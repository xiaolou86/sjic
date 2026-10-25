"""RTSP 取帧：推理要帧时交出此刻最新的一帧，按 inferFps 控制推理节拍。"""
import threading
import time

import cv2

# 连续失败这么多次，或者这么久没拿到好帧，就重连。
_RECONNECT_FAILS = 30
_RECONNECT_STALL_SEC = 10.0
_RECONNECT_DELAY_SEC = 2.0
_STATS_SEC = 5.0


def open_capture(url):
    if not url:
        return None
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def _open_for_reconnect(url):
    """重连时尽量走与主路径相同的 RtspCapture，失败再退回 raw VideoCapture。"""
    try:
        from utils.stream import open_rtsp_capture
        return open_rtsp_capture(url)
    except Exception:
        return open_capture(url)


def is_valid_frame(frame):
    if frame is None:
        return False
    try:
        return frame.size > 0 and len(frame.shape) >= 2 and frame.shape[0] >= 16
    except Exception:
        return False


def _reads_latest(cap):
    """GStreamer 源自己只留最新一帧，按需 read 即可。只有 read 的对象也只能按需读。"""
    if getattr(cap, "reads_latest", False):
        return True
    return not (callable(getattr(cap, "grab", None)) and callable(getattr(cap, "retrieve", None)))


class InferPacer:
    """推理节拍：每轮开头取此刻最新的一帧，推理用时不足一个周期就等到周期满再取下一帧。

    推理比周期慢时不等，直接开始下一轮，也不补跑落下的轮次。fps<=0 表示不限速。
    """

    def __init__(self, fps):
        try:
            fps = float(fps)
        except (TypeError, ValueError):
            fps = 0.0
        self.fps = fps if fps > 0 else 0.0
        self.interval = 1.0 / self.fps if self.fps else 0.0
        self._next = 0.0

    def wait(self, stop_event):
        """等到本轮开始。任务停了返回 False。"""
        now = time.perf_counter()
        delay = self._next - now
        if delay > 0:
            if stop_event.wait(delay):
                return False
            # 按预定时刻排下一轮，定时器多睡的那点不累积
            start = self._next
        else:
            start = now
        self._next = start + self.interval
        return not stop_event.is_set()


class FramePump:
    """交出推理要帧那一刻的最新画面。

    FFmpeg、本地文件：后台线程一直 grab，解码跟住直播（P 帧要连续参考，不能跳着解）。
    只有推理在等的时候才 retrieve，没被取走的帧不做颜色转换，也不拷进 Python。
    GStreamer：管道在自己的线程里解码，appsink 只留最新一帧，取帧时直接 read，不开线程。
    """

    def __init__(self, cap, stop_event, url, logger, open_fn=None):
        self.cap = cap
        self.stop_event = stop_event
        self.url = url
        self.logger = logger
        self.open_fn = open_fn or _open_for_reconnect
        self._direct = _reads_latest(cap)
        self._cap_lock = threading.Lock()
        self._cond = threading.Condition()
        self._frame = None
        self._frame_t = 0.0
        self._seq = 0
        self._waiting = 0
        self._fail = 0
        self._last_ok = time.perf_counter()
        self._released = False
        self._decode_n = 0
        self._consume_n = 0
        self._stats_t = time.perf_counter()
        self._warn_t = 0.0
        self._thread = None
        if not self._direct:
            self._thread = threading.Thread(target=self._grab_loop, name='rtsp-pump', daemon=True)

    def start(self):
        if self._thread is not None:
            self._thread.start()

    def _warn(self, message):
        now = time.perf_counter()
        if now - self._warn_t >= 5.0:
            self._warn_t = now
            self.logger.warning(message)

    def _maybe_log_stats(self):
        now = time.perf_counter()
        dt = now - self._stats_t
        if dt < _STATS_SEC:
            return
        backend = getattr(self.cap, "backend", type(self.cap).__name__)
        decode = "in-pipeline" if self._direct else f"{self._decode_n / dt:.1f}fps"
        self.logger.info(
            f"RTSP pump: backend={backend} decode={decode} consume={self._consume_n / dt:.1f}fps"
        )
        self._decode_n = 0
        self._consume_n = 0
        self._stats_t = now

    def _on_ok(self):
        self._fail = 0
        self._last_ok = time.perf_counter()

    def _on_fail(self):
        self._fail += 1
        stalled = time.perf_counter() - self._last_ok >= _RECONNECT_STALL_SEC
        if self._fail >= _RECONNECT_FAILS or stalled:
            self._reconnect()
            self._fail = 0
            self._last_ok = time.perf_counter()
        else:
            self.stop_event.wait(0.03)

    def _deliver(self, frame):
        with self._cond:
            self._frame = frame
            self._frame_t = time.perf_counter()
            self._seq += 1
            self._cond.notify_all()

    def _grab_loop(self):
        """一直 grab 跟住直播；推理在等时才 retrieve 这一帧。"""
        while not self.stop_event.is_set():
            frame = None
            try:
                with self._cap_lock:
                    cap = self.cap
                    ok = cap is not None and bool(cap.grab())
                    if ok and self._waiting:
                        got, frame = cap.retrieve()
                        if not got or not is_valid_frame(frame):
                            frame = None
            except Exception as e:
                if self.stop_event.is_set():
                    break
                self._warn(f"RTSP pump error: {e}")
                ok = False
            if self.stop_event.is_set():
                break
            if not ok:
                self._on_fail()
                continue
            self._on_ok()
            self._decode_n += 1
            if frame is not None:
                self._deliver(frame)
            self._maybe_log_stats()

    def _read_direct(self, last_seq, wait_sec):
        deadline = time.perf_counter() + float(wait_sec)
        while not self.stop_event.is_set():
            ok, frame = False, None
            try:
                with self._cap_lock:
                    if self.cap is not None:
                        ok, frame = self.cap.read()
            except Exception as e:
                self._warn(f"RTSP read error: {e}")
            if ok and is_valid_frame(frame):
                self._on_ok()
                with self._cond:
                    self._seq += 1
                    seq = self._seq
                self._consume_n += 1
                self._maybe_log_stats()
                return frame, seq
            if self.stop_event.is_set():
                break
            self._on_fail()
            if time.perf_counter() >= deadline:
                break
        return None, last_seq

    def get_latest(self, last_seq=0, wait_sec=1.0):
        """返回 (frame, seq)：调用之后才取出的那一帧，也就是此刻最新的画面。

        等不到返回 (None, last_seq)。frame 是独立数组，推理随意改写不影响后续取帧。
        """
        if self._direct:
            return self._read_direct(last_seq, wait_sec)
        asked = time.perf_counter()
        deadline = asked + float(wait_sec)
        with self._cond:
            self._waiting += 1
            try:
                while not self.stop_event.is_set():
                    if self._frame is not None and self._frame_t >= asked and self._seq > last_seq:
                        self._consume_n += 1
                        return self._frame, self._seq
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        break
                    self._cond.wait(min(remaining, 0.25))
            finally:
                self._waiting -= 1
        return None, last_seq

    def _take_cap(self):
        with self._cap_lock:
            cap = self.cap
            self.cap = None
            return cap

    def _close_cap(self, cap):
        if cap is None:
            return
        try:
            cap.release()
        except Exception:
            pass

    def _reconnect(self):
        if self.stop_event.is_set():
            return
        self.logger.warning("RTSP pump reconnecting...")
        self._close_cap(self._take_cap())
        if self.stop_event.wait(_RECONNECT_DELAY_SEC):
            return
        try:
            cap = self.open_fn(self.url)
        except Exception as e:
            self.logger.error(f"RTSP pump reconnect failed: {e}")
            self.stop_event.wait(1.0)
            return
        if cap is None or not cap.isOpened():
            self.logger.error("RTSP pump reconnect failed")
            self._close_cap(cap)
            self.stop_event.wait(1.0)
            return
        with self._cap_lock:
            if self.stop_event.is_set():
                self._close_cap(cap)
                return
            self.cap = cap
        self.logger.info(f"RTSP pump reconnected backend={getattr(cap, 'backend', '?')}")

    def release(self):
        """先等取帧线程离开 OpenCV native 调用，再释放 VideoCapture，避免 heap corruption。"""
        if self._released:
            return
        self._released = True
        self.stop_event.set()
        with self._cond:
            self._cond.notify_all()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15.0)
            if thread.is_alive():
                self.logger.warning(
                    "RTSP pump still running after stop; waiting for in-flight grab before release"
                )
        self._close_cap(self._take_cap())
        with self._cond:
            self._frame = None
