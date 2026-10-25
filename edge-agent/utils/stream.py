"""RTSP 取流。

H.264/H.265 的 P 帧参考前面的帧，解码只能一帧不落地跟着直播走。
能省的是解码之后的活：只有推理来取的那一帧才转成 BGR、拷进 Python。

打开顺序：
1. GStreamer 硬解：Jetson nvv4l2decoder、桌面 NVIDIA nvh264dec、RK mppvideodec。
   有 PyGObject（python3-gi）时直连 appsink；否则用 OpenCV 编进去的 GStreamer 后端。
   pip 装的 opencv-python 不带 GStreamer，两条都没有时跳过。
2. OpenCV FFmpeg，TCP 拉流。
3. GStreamer 软解（avdec），最后退回 OpenCV 默认后端。
"""
import ctypes
import logging
import os
import subprocess
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger('utils.stream')

# 只保留 TCP。多余 option 在部分 OpenCV/FFmpeg 上会让整串参数失效，回退成 UDP。
_FFMPEG_TCP_OPTIONS = "rtsp_transport;tcp"
# FFmpeg 的超时只认打开时传入的参数，打开后再 set 不生效。
_OPEN_TIMEOUT_MS = 10000
_READ_TIMEOUT_MS = 5000
# GStreamer 直播源每次取帧最多等这么久。
_LIVE_WAIT_SEC = 2.0
# 新管道要等第一个关键帧才出图，有的摄像头 GOP 很长。
_FIRST_FRAME_SEC = 10.0
# 直接 read 时追到直播最新处的上限。解码追不上直播就先交这一帧，下次接着追。
_DRAIN_BUDGET_SEC = 1.0
_MAX_DRAIN_FRAMES = 120
_PROBE_ELEMENTS = (
    "rtspsrc", "nvv4l2decoder", "nvvidconv", "nvh264dec", "nvh265dec", "mppvideodec", "avdec_h264",
)
_YUV420_TO_BGR = {
    "NV12": cv2.COLOR_YUV2BGR_NV12,
    "NV21": cv2.COLOR_YUV2BGR_NV21,
    "I420": cv2.COLOR_YUV2BGR_I420,
    "YV12": cv2.COLOR_YUV2BGR_YV12,
}

_GST_LOCK = threading.Lock()
_GST = None  # None 还没探测；False 不可用
_CV_GST = None
_GST_ELEM_CACHE = {}
_GST_SUCCESS = {}  # rtsp_url -> (pipeline, label, fmt)
_DECODE_PROBE_LOGGED = False


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


def is_local_media_file(url):
    """本地视频文件没有直播时钟，grab 会立刻返回下一帧。"""
    if not isinstance(url, str):
        return False
    text = url.strip()
    if not text:
        return False
    low = text.lower()
    if low.startswith("file://"):
        return True
    if low.startswith((
        "rtsp://", "rtsps://", "rtmp://", "http://", "https://",
        "udp://", "tcp://", "image-set:",
    )):
        return False
    if text.isdigit() or text.startswith("/dev/") or text.startswith("\\\\.\\"):
        return False
    return True


def _hwdec_wanted():
    v = os.environ.get("SJIC_RTSP_HWDEC", "1").strip().lower()
    return v not in ("0", "false", "off", "cpu", "no")


def _mask_url(url):
    """日志里不带摄像头账号密码。"""
    location, username, password = _split_rtsp_auth(url)
    if not username and not password:
        return str(url or "")
    return location.replace("://", "://***@", 1)


def _gst_quote(value):
    """gst-launch 双引号字符串。密码里的 @、! 不能露在引号外面。"""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _split_rtsp_auth(url):
    """拆出账号密码。密码里可以有 @，按主机前的最后一个 @ 切。

    返回 (不带账号的地址, 用户名, 密码)。没有账号时地址原样返回。
    """
    from urllib.parse import unquote

    text = str(url or "").strip()
    head, sep, rest = text.partition("://")
    if not sep:
        return text, "", ""
    authority, slash, tail = rest.partition("/")
    userinfo, at, hostport = authority.rpartition("@")
    if not at or not hostport:
        return text, "", ""
    username, colon, password = userinfo.partition(":")
    if not colon:
        password = ""
    location = f"{head}://{hostport}{slash}{tail}"
    return location, unquote(username), unquote(password)


def _rtspsrc(rtsp_url):
    """rtspsrc 片段。账号密码用属性传递，不写进 location。

    GStreamer 按第一个 @ 切 RTSP 地址。密码里再有 @（例如 cloud@123）时，
    写在 location 里会被当成主机名，摄像头返回 401，硬解管道就被放弃。
    """
    location, username, password = _split_rtsp_auth(rtsp_url)
    auth = ""
    if username or password:
        auth = f" user-id={_gst_quote(username)} user-pw={_gst_quote(password)}"
    return (
        f"rtspsrc location={_gst_quote(location)}{auth} protocols=tcp latency=200 retry=5 "
        f"timeout=5000000 tcp-timeout=5000000 drop-on-latency=true"
    )


def _gi_gst():
    """PyGObject 的 Gst 模块；没装 python3-gi 时返回 None。"""
    global _GST
    with _GST_LOCK:
        if _GST is None:
            try:
                import gi
                gi.require_version("Gst", "1.0")
                from gi.repository import Gst
                Gst.init(None)
                _GST = Gst
            except Exception as exc:
                logger.debug("PyGObject GStreamer unavailable: %s", exc)
                _GST = False
        return _GST or None


def _cv_has_gstreamer():
    global _CV_GST
    if _CV_GST is None:
        try:
            line = next(
                (row for row in cv2.getBuildInformation().splitlines()
                 if row.strip().startswith("GStreamer:")),
                "",
            )
            _CV_GST = "YES" in line.upper()
        except Exception:
            _CV_GST = False
    return _CV_GST


def _gst_has_element(name):
    cached = _GST_ELEM_CACHE.get(name)
    if cached is not None:
        return cached
    Gst = _gi_gst()
    if Gst is not None:
        ok = Gst.ElementFactory.find(name) is not None
    else:
        try:
            r = subprocess.run(
                ["gst-inspect-1.0", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            ok = r.returncode == 0
        except Exception:
            ok = False
    _GST_ELEM_CACHE[name] = ok
    return ok


def _nvdec_kind():
    """jetson / nvidia / ''。看设备节点，不依赖 config.yaml 是否填对。"""
    if os.path.exists("/dev/nvhost-nvdec") or os.path.exists("/dev/nvhost-ctrl-gpu"):
        return "jetson"
    if os.path.exists("/dev/nvidia0"):
        return "nvidia"
    return ""


def _log_decode_probe_once():
    """进程里第一次开流时写一行：Python 能不能用 GStreamer，容器里有哪些解码插件。"""
    global _DECODE_PROBE_LOGGED
    if _DECODE_PROBE_LOGGED:
        return
    _DECODE_PROBE_LOGGED = True
    hw = _hwdec_wanted()
    gi_ok = _gi_gst() is not None
    cv_ok = _cv_has_gstreamer()
    elems = [name for name in _PROBE_ELEMENTS if _gst_has_element(name)]
    logger.info(
        "RTSP decode probe: hwdec=%s nvdec_dev=%s pygobject=%s opencv_gstreamer=%s gst_elements=%s",
        "on" if hw else "off",
        _nvdec_kind() or "none",
        gi_ok,
        cv_ok,
        elems or "none",
    )
    if hw and not gi_ok and not cv_ok:
        logger.warning(
            "RTSP 用不了 GStreamer 硬解：没装 PyGObject（python3-gi），OpenCV 也没编 GStreamer。"
            "实时流走 FFmpeg CPU 软解"
        )


def _gst_candidates(rtsp_url):
    """返回 (硬解管道, 软解管道)，每项是 (管道, 标签, appsink 格式)。

    appsink 只留最新一帧，推理没来取的帧在这里丢掉，解码器不会被堵住，延时也不会越积越长。
    appsink 收解码器原生格式（Jetson 由 VIC 转成 BGRx），推理取走的那一帧才转 BGR。
    格式为 BGR 的是带 videoconvert 的旧管道，只给读不了原生格式的老 OpenCV 用。
    """
    src = _rtspsrc(rtsp_url)
    sink = "appsink name=sink max-buffers=1 drop=true sync=false"

    def chain(codec, decoder, fmt, label):
        head = f"{src} ! rtp{codec}depay ! {codec}parse ! {decoder} ! video/x-raw,format={fmt}"
        name = f"{label}-{codec}"
        return [
            (f"{head} ! {sink}", name, fmt),
            (f"{head} ! videoconvert ! video/x-raw,format=BGR ! {sink}", name, "BGR"),
        ]

    hw = _hwdec_wanted()
    kind = _nvdec_kind() if hw else ""
    jetson = hw and (kind == "jetson" or _gst_has_element("nvv4l2decoder"))
    desktop = hw and not jetson and (
        kind == "nvidia" or _gst_has_element("nvh264dec") or _gst_has_element("nvh265dec")
    )
    rk = hw and not jetson and not desktop and (
        _gst_has_element("mppvideodec")
        or os.path.exists("/dev/mpp_service")
        or os.path.exists("/dev/rkvdec")
    )
    hw_out, cpu_out = [], []
    for codec in ("h264", "h265"):
        if jetson:
            # NVDEC 解码，VIC 转成系统内存里的 BGRx，CPU 不做颜色转换
            hw_out += chain(codec, "nvv4l2decoder ! nvvidconv", "BGRx", "gstreamer-nvdec")
        elif desktop:
            hw_out += chain(codec, f"nv{codec}dec", "NV12", "gstreamer-nvdec")
        elif rk:
            hw_out += chain(codec, "mppvideodec", "NV12", "gstreamer-mpp")
        cpu_out += chain(codec, f"avdec_{codec}", "I420", "gstreamer-cpu")
    return hw_out, cpu_out


def _round_up(value, align):
    return (value + align - 1) // align * align


def _packed_rows(buf, height, row_bytes):
    """单平面格式按总长求行宽，去掉行尾对齐。"""
    if height <= 0 or buf.size < height * row_bytes or buf.size % height:
        raise ValueError(f"{buf.size} bytes do not fit {height} rows of {row_bytes}")
    return buf.reshape(height, buf.size // height)[:, :row_bytes]


def _yuv420_layout(size, semi, width, height):
    """按总长反推 YUV420 的行宽和平面高度。解码器常把宽高补齐到 16/32/64。

    返回 (亮度行宽, 色度行宽, 各色度平面起点)；对不上返回 None。
    """
    for v_align in (2, 8, 16, 32, 64):
        rows = _round_up(height, v_align)
        for h_align in (4, 8, 16, 32, 64, 128, 256):
            y_stride = _round_up(width, h_align)
            first = y_stride * rows
            if semi:
                if first + y_stride * (rows // 2) == size:
                    return y_stride, y_stride, [first]
                continue
            for c_stride in (_round_up(width // 2, 4), y_stride // 2):
                second = first + c_stride * (rows // 2)
                if second + c_stride * (rows // 2) == size:
                    return y_stride, c_stride, [first, second]
    return None


def _yuv420_planes(buf, name, width, height):
    """拼成 OpenCV 要的紧凑 YUV420，形状 (h*3/2, w)。没有补齐时不拷贝。"""
    if width % 2 or height % 2:
        raise ValueError(f"YUV420 needs even size, got {width}x{height}")
    if buf.size == width * height * 3 // 2:
        return buf.reshape(height * 3 // 2, width)
    semi = name in ("NV12", "NV21")
    layout = _yuv420_layout(buf.size, semi, width, height)
    if layout is None:
        raise ValueError(f"cannot map {name} {width}x{height} from {buf.size} bytes")
    y_stride, c_stride, starts = layout
    out = np.empty((height * 3 // 2, width), dtype=np.uint8)
    out[:height] = buf[:y_stride * height].reshape(height, y_stride)[:, :width]
    half = height // 2
    if semi:
        start = starts[0]
        out[height:] = buf[start:start + c_stride * half].reshape(half, c_stride)[:, :width]
        return out
    flat = out.reshape(-1)
    cw = width // 2
    pos = width * height
    for start in starts:
        plane = buf[start:start + c_stride * half].reshape(half, c_stride)[:, :cw]
        flat[pos:pos + cw * half] = plane.reshape(-1)
        pos += cw * half
    return out


def raw_to_bgr(data, fmt, width, height):
    """appsink 的原始帧转 BGR，返回新数组。"""
    buf = np.frombuffer(data, dtype=np.uint8)
    w, h = int(width), int(height)
    name = str(fmt or "").upper()
    if name in ("BGRX", "BGRA", "RGBX", "RGBA"):
        img = _packed_rows(buf, h, w * 4).reshape(h, w, 4)
        code = cv2.COLOR_BGRA2BGR if name.startswith("BGR") else cv2.COLOR_RGBA2BGR
        return cv2.cvtColor(img, code)
    if name in ("BGR", "RGB"):
        img = _packed_rows(buf, h, w * 3).reshape(h, w, 3)
        return img.copy() if name == "BGR" else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    code = _YUV420_TO_BGR.get(name)
    if code is None:
        raise ValueError(f"unsupported appsink format {fmt}")
    return cv2.cvtColor(_yuv420_planes(buf, name, w, h), code)


def _cv_gst_to_bgr(raw, fmt):
    """OpenCV GStreamer 后端交出的原始帧转 BGR：四通道去掉 alpha，YUV420 按格式换色。"""
    if raw.ndim == 3 and raw.shape[2] == 3:
        return raw
    if raw.ndim == 3 and raw.shape[2] == 4:
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    code = _YUV420_TO_BGR.get(str(fmt or "").upper())
    if raw.ndim == 2 and code is not None:
        return cv2.cvtColor(raw, code)
    raise ValueError(f"unexpected frame {raw.shape} for format {fmt}")


def _is_bgr(frame):
    return frame is not None and frame.ndim == 3 and frame.shape[2] == 3 and frame.size > 0


class _GstAppSink:
    """PyGObject 直连 appsink。解码在 GStreamer 自己的线程里跟着直播走，不占 Python 线程。"""

    def __init__(self, Gst, pipeline, label):
        self._Gst = Gst
        self.label = label
        self.error = ""
        self.resource_error = False
        self._failed = False
        self._lock = threading.Lock()
        self._sample = None
        self._size = (0, 0)
        self._fps = 0.0
        self._pipeline = Gst.parse_launch(pipeline)
        self._sink = self._pipeline.get_by_name("sink")
        self._bus = self._pipeline.get_bus()
        if self._sink is None:
            self.release()
            raise RuntimeError("pipeline has no appsink named sink")
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._drain_bus()
            reason = self.error or "cannot set pipeline to PLAYING"
            self.release()
            raise ConnectionError(reason)

    def _drain_bus(self):
        """取空总线。只认错误和结束；其余消息丢掉，常驻进程里不能越积越多。"""
        Gst = self._Gst
        failed = False
        while self._bus is not None:
            msg = self._bus.pop()
            if msg is None:
                break
            if msg.type == Gst.MessageType.ERROR:
                err, _debug = msg.parse_error()
                self.error = getattr(err, "message", None) or str(err)
                self.resource_error = "resource" in str(getattr(err, "domain", ""))
                failed = True
            elif msg.type == Gst.MessageType.EOS:
                self.error = "end of stream"
                failed = True
        return failed

    def grab(self, timeout=_LIVE_WAIT_SEC):
        """取 appsink 里此刻最新的一帧；上一帧刚被取走就等下一帧到。"""
        Gst = self._Gst
        deadline = time.monotonic() + float(timeout)
        while True:
            with self._lock:
                if self._sink is None or self._failed:
                    return False
                if self._drain_bus():
                    self._failed = True
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                sample = self._sink.emit("try-pull-sample", int(min(remaining, 0.25) * Gst.SECOND))
                if sample is not None:
                    self._sample = sample
                    return True

    def retrieve(self):
        with self._lock:
            sample = self._sample
        if sample is None:
            return False, None
        try:
            caps = sample.get_caps().get_structure(0)
            width = caps.get_value("width")
            height = caps.get_value("height")
            ok, num, den = caps.get_fraction("framerate")
            if ok and den:
                self._fps = num / den
            buf = sample.get_buffer()
            frame = raw_to_bgr(buf.extract_dup(0, buf.get_size()), caps.get_value("format"), width, height)
        except Exception as exc:
            self.error = str(exc)
            return False, None
        self._size = (width, height)
        return True, frame

    def read(self, timeout=_LIVE_WAIT_SEC):
        if not self.grab(timeout):
            return False, None
        return self.retrieve()

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self._size[0])
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self._size[1])
        if prop == cv2.CAP_PROP_FPS:
            return float(self._fps)
        return 0.0

    def set(self, prop, value):
        return False

    def isOpened(self):
        return self._pipeline is not None and not self._failed

    def release(self):
        with self._lock:
            pipeline = self._pipeline
            self._pipeline = None
            self._sink = None
            self._bus = None
            self._sample = None
        if pipeline is not None:
            try:
                pipeline.set_state(self._Gst.State.NULL)
            except Exception:
                pass


class _CvGst:
    """OpenCV 的 GStreamer 后端。appsink 同样只留最新一帧，retrieve 之后才转 BGR。"""

    def __init__(self, pipeline, label, fmt):
        self.label = label
        self.error = ""
        self.resource_error = False
        self._fmt = fmt
        self._timeout_ms = None
        self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self._cap.isOpened():
            self._cap.release()
            raise ConnectionError("pipeline did not start")

    def _set_timeout(self, sec):
        prop = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
        ms = max(1, int(float(sec) * 1000))
        if prop is None or ms == self._timeout_ms:
            return
        try:
            self._cap.set(prop, ms)
        except Exception:
            pass
        self._timeout_ms = ms

    def grab(self, timeout=_LIVE_WAIT_SEC):
        self._set_timeout(timeout)
        return bool(self._cap.grab())

    def retrieve(self):
        try:
            ok, raw = self._cap.retrieve()
            if not ok or raw is None:
                return False, None
            return True, _cv_gst_to_bgr(raw, self._fmt)
        except Exception as exc:
            self.error = str(exc)
            return False, None

    def read(self, timeout=_LIVE_WAIT_SEC):
        if not self.grab(timeout):
            return False, None
        return self.retrieve()

    def get(self, prop):
        return self._cap.get(prop)

    def set(self, prop, value):
        return self._cap.set(prop, value)

    def isOpened(self):
        return self._cap.isOpened()

    def release(self):
        self._cap.release()


def _open_gst(rtsp_url, candidates):
    """依次试管道，第一帧能转成 BGR 才算打开。返回 (source, 标签)。"""
    Gst = _gi_gst()
    if Gst is None and not _cv_has_gstreamer():
        return None, None
    flavor = "pygobject" if Gst is not None else "opencv"
    if Gst is not None:
        # PyGObject 自己转原生格式，用不上带 videoconvert 的旧管道
        candidates = [c for c in candidates if c[2] != "BGR"]
    cached = _GST_SUCCESS.get(rtsp_url)
    if cached in candidates:
        candidates = [cached] + [c for c in candidates if c != cached]
    for pipeline, label, fmt in candidates:
        source = None
        reason = "no frame"
        try:
            if Gst is not None:
                source = _GstAppSink(Gst, pipeline, label)
            else:
                source = _CvGst(pipeline, label, fmt)
            ok, frame = source.read(_FIRST_FRAME_SEC)
            if ok and _is_bgr(frame):
                _GST_SUCCESS[rtsp_url] = (pipeline, label, fmt)
                logger.info(
                    "Opened RTSP via %s (%s, appsink %s) %dx%d",
                    label, flavor, fmt, frame.shape[1], frame.shape[0],
                )
                return source, label
            reason = getattr(source, "error", "") or reason
        except Exception as exc:
            reason = str(exc)
        unreachable = bool(getattr(source, "resource_error", False))
        if source is not None:
            source.release()
        logger.info("%s (%s, appsink %s) unavailable: %s", label, flavor, fmt, reason)
        if unreachable:
            # 连不上摄像头或打不开解码设备，换下一条管道也一样
            break
    return None, None


def _ffmpeg_params():
    params = []
    for name, value in (
        ("CAP_PROP_OPEN_TIMEOUT_MSEC", _OPEN_TIMEOUT_MS),
        ("CAP_PROP_READ_TIMEOUT_MSEC", _READ_TIMEOUT_MS),
    ):
        prop = getattr(cv2, name, None)
        if prop is not None:
            params += [prop, value]
    hw_prop = getattr(cv2, "CAP_PROP_HW_ACCELERATION", None)
    hw_any = getattr(cv2, "VIDEO_ACCELERATION_ANY", None)
    if _hwdec_wanted() and hw_prop is not None and hw_any is not None:
        # 编译时没带硬件加速的 FFmpeg 会静默走软解
        params += [hw_prop, hw_any]
    return params


def _open_ffmpeg(url):
    _configure_ffmpeg_tcp()
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, _ffmpeg_params())
    except Exception:
        # 4.5.2 之前的 OpenCV 不收打开参数
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        return None, None
    accel = 0
    hw_prop = getattr(cv2, "CAP_PROP_HW_ACCELERATION", None)
    if hw_prop is not None:
        try:
            accel = int(cap.get(hw_prop) or 0)
        except Exception:
            accel = 0
    logger.info("Opened RTSP via FFmpeg TCP (%s)", f"hw decode type={accel}" if accel > 0 else "cpu decode")
    return cap, ("ffmpeg-hw" if accel > 0 else "ffmpeg")


def _open_raw(rtsp_url, local=False):
    """GStreamer 硬解 → FFmpeg → GStreamer 软解 → OpenCV 默认。返回 (cap, 后端标签)。"""
    cap, label = None, None
    if not local:
        _log_decode_probe_once()
        hw, cpu = _gst_candidates(rtsp_url)
        cap, label = _open_gst(rtsp_url, hw)
        if cap is None:
            cap, label = _open_ffmpeg(rtsp_url)
        if cap is None:
            cap, label = _open_gst(rtsp_url, cpu)
    else:
        cap, label = _open_ffmpeg(rtsp_url)
    if cap is not None:
        return cap, label

    logger.warning("FFmpeg TCP open failed, falling back to OpenCV default: %s", _mask_url(rtsp_url))
    cap = cv2.VideoCapture(rtsp_url)
    if cap.isOpened():
        return cap, "opencv-default"
    cap.release()
    return None, None


class RtspCapture:
    """一路视频源。

    reads_latest 为 True（GStreamer）：appsink 只留最新一帧，read 拿到的就是此刻的画面，
    不需要后台线程。
    为 False（FFmpeg、本地文件）：grab 一次解一帧，要有线程一直 grab 跟住直播，
    推理来取时再 retrieve。FramePump 按这个属性决定怎么取帧。
    本地文件没有直播时钟，grab 按开播后的墙钟对齐片内时间戳；落后就跳过这段时间里的帧。
    """

    def __init__(self, rtsp_url):
        self._url = rtsp_url
        self._cap = None
        self.backend = "ffmpeg"
        self.reads_latest = False
        self._fps = 25.0
        self._local_file = is_local_media_file(rtsp_url)
        self._clock_start = None
        self._origin_pts = 0.0
        self._last_pts = 0.0
        self._gap_ms = 0.0
        self._lock = threading.Lock()

    def start(self):
        _silence_libav_logs()
        cap, backend = _open_raw(self._url, local=self._local_file)
        if cap is None:
            raise ConnectionError(f"Cannot open camera stream at {_mask_url(self._url)}")
        self._cap = cap
        self.backend = backend
        self.reads_latest = backend.startswith("gstreamer")
        fps = cap.get(cv2.CAP_PROP_FPS)
        self._fps = fps if fps and 1.0 < fps <= 240.0 else 25.0
        logger.info("RTSP ready backend=%s fps=%.1f", backend, self._fps)
        return self

    def _frame_gap_ms(self):
        gap = self._gap_ms
        if 1.0 <= gap <= 1000.0:
            return gap
        fps = self._fps
        if fps and 1.0 < fps <= 240.0:
            return 1000.0 / float(fps)
        return 40.0

    def _note_pts(self, pts):
        """用容器时间戳推进播放头。时间戳不走或跳变时，按上一帧间隔补。"""
        gap = pts - self._last_pts
        if 1.0 <= gap <= 1000.0:
            self._gap_ms = gap
            self._last_pts = pts
            return
        self._last_pts += self._frame_gap_ms()

    def _grab_aligned(self):
        """返回墙钟对应的那一帧。还没到点就等，已经落后就连续 grab 跳过去。"""
        while True:
            sleep_for = 0.0
            with self._lock:
                cap = self._cap
                if cap is None:
                    return False
                now = time.perf_counter()
                if self._clock_start is None:
                    if not cap.grab():
                        return False
                    pts = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                    self._clock_start = now
                    self._origin_pts = pts
                    self._last_pts = pts
                    return True
                media_now = self._origin_pts + (now - self._clock_start) * 1000.0
                gap = self._frame_gap_ms()
                if media_now < self._last_pts + gap:
                    sleep_for = (self._last_pts + gap - media_now) / 1000.0
                else:
                    started = time.perf_counter()
                    while True:
                        if not cap.grab():
                            return False
                        pts = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                        self._note_pts(pts)
                        now = time.perf_counter()
                        media_now = self._origin_pts + (now - self._clock_start) * 1000.0
                        gap = self._frame_gap_ms()
                        if media_now < self._last_pts + gap:
                            return True
                        if now - started > 0.2:
                            return True
            if sleep_for > 0:
                time.sleep(min(sleep_for, 1.0))

    def grab(self):
        """解一帧。直播源由 FramePump 的线程连续调用；本地文件按墙钟节奏出帧。"""
        if self._local_file:
            return self._grab_aligned()
        with self._lock:
            cap = self._cap
            return cap is not None and bool(cap.grab())

    def retrieve(self):
        with self._lock:
            if self._cap is None:
                return False, None
            return self._cap.retrieve()

    def read(self):
        """没有 FramePump 的调用方直接 read，拿到的也是此刻最新一帧。"""
        if self._local_file:
            if not self._grab_aligned():
                return False, None
            return self.retrieve()
        with self._lock:
            cap = self._cap
            if cap is None:
                return False, None
            if self.reads_latest:
                return cap.read(_LIVE_WAIT_SEC)
            if drain_to_live(cap, self._frame_gap_ms() / 1000.0) <= 0:
                return False, None
            return cap.retrieve()

    def get(self, prop):
        with self._lock:
            if self._cap is None:
                return 0
            return self._cap.get(prop)

    def set(self, prop, value):
        with self._lock:
            if self._cap is None:
                return False
            return self._cap.set(prop, value)

    def isOpened(self):
        with self._lock:
            return self._cap is not None and self._cap.isOpened()

    def release(self):
        with self._lock:
            cap = self._cap
            self._cap = None
            if cap is None:
                return
            try:
                cap.release()
            except Exception:
                pass


def drain_to_live(cap, frame_gap_sec):
    """连续 grab 解掉已经到达的旧帧，追到直播最新处。返回成功 grab 的次数。

    缓冲里的帧 grab 得很快；某次 grab 要等网络送来下一帧，说明这一帧就是此刻最新的。
    解码追不上直播时到点就停，下次再追。
    """
    if cap is None:
        return 0
    live_wait = max(0.008, float(frame_gap_sec or 0.04) * 0.5)
    taken = 0
    started = time.perf_counter()
    for _ in range(_MAX_DRAIN_FRAMES):
        t0 = time.perf_counter()
        try:
            ok = bool(cap.grab())
        except Exception:
            ok = False
        if not ok:
            break
        taken += 1
        now = time.perf_counter()
        if now - t0 >= live_wait or now - started >= _DRAIN_BUDGET_SEC:
            break
    return taken


def open_rtsp_capture(rtsp_url):
    """打开视频源，返回 RtspCapture。

    image-set: 是平台图片测试流：边缘拉一张静图后反复送出，不走解码。
    """
    if rtsp_url is None or (isinstance(rtsp_url, str) and not rtsp_url.strip()):
        raise ValueError("rtsp_url is empty")
    if isinstance(rtsp_url, str) and rtsp_url.strip().startswith('image-set:'):
        from utils.image_set import open_image_set_capture
        return open_image_set_capture(rtsp_url.strip())
    return RtspCapture(rtsp_url).start()


_silence_libav_logs()
