import ctypes
import logging
import os
import time

import cv2

logger = logging.getLogger('utils.stream')

# 只保留 TCP。多余 option 在部分 OpenCV/FFmpeg 上会让整串参数失效，回退成 UDP。
_FFMPEG_TCP_OPTIONS = "rtsp_transport;tcp"
_MAX_SKIP_FRAMES = 15


def _silence_libav_logs():
    """压掉 FFmpeg 打到 stderr 的 H.264 MB / RTP 解码噪声。"""
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass
    try:
        cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
    except Exception:
        pass

    for name in (
        getattr(cv2, "__file__", None),
        "libavutil.so.59",
        "libavutil.so.58",
        "libavutil.so.57",
        "libavutil.so.56",
        "libavutil.so",
    ):
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            lib.av_log_set_level(8)  # AV_LOG_FATAL，低于 ERROR
        except Exception:
            continue


def _configure_ffmpeg_tcp():
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _FFMPEG_TCP_OPTIONS
    os.environ.setdefault("OPENCV_FFMPEG_READ_ATTEMPTS", "65536")
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")


def _gst_pipeline(rtsp_url):
    location = rtsp_url.replace("\\", "\\\\").replace('"', '\\"')
    # leaky queue 放在解码器前面：推理期间 Python 不 read 时解码器堵住，
    # 旧压缩包在这里丢掉，只保留最新一包。appsink 不 drop，避免空转解码。
    return (
        f'rtspsrc location="{location}" protocols=tcp latency=200 retry=5 '
        f'drop-on-latency=true ! '
        f'rtph264depay ! h264parse ! '
        f'queue leaky=downstream max-size-buffers=1 max-size-time=0 max-size-bytes=0 ! '
        f'avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! '
        f'appsink max-buffers=1 drop=false sync=false'
    )


def _tune_cap(cap):
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
    except Exception:
        pass
    return cap


def _open_raw(rtsp_url):
    """GStreamer-TCP（解码前丢旧包）→ FFmpeg-TCP → 默认。返回 (cap, backend)。"""
    gst = _gst_pipeline(rtsp_url)
    if hasattr(cv2, "CAP_GSTREAMER"):
        cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            logger.info("Opened RTSP via GStreamer TCP (drop-old-before-decode)")
            return _tune_cap(cap), "gstreamer"
        cap.release()
        logger.info("GStreamer TCP unavailable, trying FFmpeg TCP")

    _configure_ffmpeg_tcp()
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if cap.isOpened():
        logger.info("Opened RTSP via FFmpeg TCP")
        return _tune_cap(cap), "ffmpeg"
    cap.release()

    logger.warning("FFmpeg TCP open failed, falling back to default (likely UDP): %s", rtsp_url)
    cap = cv2.VideoCapture(rtsp_url)
    if cap.isOpened():
        return _tune_cap(cap), "ffmpeg"
    cap.release()
    return None, None


class RtspCapture:
    """
    推理线程按需取最新帧，没有后台解码线程。

    GStreamer：解码器前 leaky queue，不 read 时只收包、丢旧压缩帧，CPU 接近空闲。
    FFmpeg：TCP 把包堆在内核；下次 grab 按间隔跳过积压帧，再 retrieve 当前这一帧。
    """

    def __init__(self, rtsp_url):
        self._url = rtsp_url
        self._cap = None
        self._backend = "ffmpeg"
        self._fps = 25.0
        self._last_grab = 0.0

    def start(self):
        _silence_libav_logs()
        cap, backend = _open_raw(self._url)
        if cap is None:
            raise ConnectionError(f"Cannot open camera stream at {self._url}")
        self._cap = cap
        self._backend = backend
        fps = cap.get(cv2.CAP_PROP_FPS)
        self._fps = fps if fps and fps > 1 else 25.0
        self._last_grab = 0.0
        logger.info("RTSP ready backend=%s fps=%.1f", backend, self._fps)
        return self

    def _discard_stale(self):
        """丢掉推理期间积压的旧帧，只解/保留最新一帧。GStreamer 管道已在压缩域丢弃。"""
        if self._cap is None or self._backend == "gstreamer":
            return
        if self._last_grab <= 0:
            return
        elapsed = time.time() - self._last_grab
        skip = int(elapsed * self._fps) - 1
        skip = min(max(skip, 0), _MAX_SKIP_FRAMES)
        for _ in range(skip):
            if not self._cap.grab():
                break

    def grab(self):
        if self._cap is None:
            return False
        self._discard_stale()
        ok = self._cap.grab()
        if ok:
            self._last_grab = time.time()
        return ok

    def retrieve(self):
        if self._cap is None:
            return False, None
        return self._cap.retrieve()

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def get(self, prop):
        if self._cap is None:
            return 0
        return self._cap.get(prop)

    def set(self, prop, value):
        if self._cap is None:
            return False
        return self._cap.set(prop, value)

    def isOpened(self):
        return self._cap is not None and self._cap.isOpened()

    def release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


def open_rtsp_capture(rtsp_url, buffer_size=1, warmup_grabs=5):
    """打开 RTSP。grab/read 时跳到最新帧，无后台读流线程。"""
    if not rtsp_url:
        raise ValueError("rtsp_url is empty")
    _ = buffer_size, warmup_grabs
    return RtspCapture(rtsp_url).start()


_silence_libav_logs()
