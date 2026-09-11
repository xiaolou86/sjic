"""RTSP 拉流：后台持续 grab，避免推理阻塞导致 UDP 丢包/重连。"""
import threading
import time

import cv2


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


class FramePump:
    """独立线程读流，主循环只取最新帧。"""

    def __init__(self, cap, stop_event, url, logger, open_fn=None):
        self.cap = cap
        self.stop_event = stop_event
        self.url = url
        self.logger = logger
        self.open_fn = open_fn or _open_for_reconnect
        self._lock = threading.Lock()
        self._cap_lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._fail = 0
        self._released = False
        self._thread = threading.Thread(target=self._loop, name='rtsp-pump', daemon=True)

    def start(self):
        self._thread.start()

    def _store(self, frame):
        with self._lock:
            self._frame = frame
            self._seq += 1
            self._fail = 0

    def _read_one(self):
        """grab+retrieve 必须在同一把锁里，禁止 stop 线程在两步之间 release。"""
        with self._cap_lock:
            if self.stop_event.is_set() or self.cap is None:
                return False, None
            if not self.cap.grab():
                return False, None
            return self.cap.retrieve()

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
        old = self._take_cap()
        self._close_cap(old)
        for _ in range(20):
            if self.stop_event.is_set():
                return
            time.sleep(0.1)
        if self.stop_event.is_set():
            return
        try:
            cap = self.open_fn(self.url)
        except Exception as e:
            self.logger.error(f"RTSP pump reconnect failed: {e}")
            time.sleep(1)
            return
        if cap is None or not cap.isOpened():
            self.logger.error("RTSP pump reconnect failed")
            self._close_cap(cap)
            time.sleep(1)
            return
        with self._cap_lock:
            if self.stop_event.is_set():
                self._close_cap(cap)
                return
            self.cap = cap
            self._fail = 0
        self.logger.info("RTSP pump reconnected")

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                ret, frame = self._read_one()
                if self.stop_event.is_set():
                    break
                if not ret:
                    self._fail += 1
                    if self._fail >= 30:
                        self._reconnect()
                    else:
                        time.sleep(0.03)
                    continue
                if is_valid_frame(frame):
                    self._store(frame)
                else:
                    self._fail += 1
            except Exception as e:
                if self.stop_event.is_set():
                    break
                self.logger.warning(f"RTSP pump error: {e}")
                self._fail += 1
                time.sleep(0.05)

    def get_latest(self, last_seq=0, wait_sec=1.0):
        """返回 (frame_copy, seq)。无新帧时 frame 为 None。"""
        deadline = time.time() + wait_sec
        while not self.stop_event.is_set():
            with self._lock:
                seq = self._seq
                frame = self._frame
            if seq > last_seq and frame is not None:
                return frame.copy(), seq
            if time.time() >= deadline:
                return None, last_seq
            time.sleep(0.01)
        return None, last_seq

    def release(self):
        """先等泵线程离开 OpenCV native 调用，再释放 VideoCapture，避免 heap corruption。"""
        if self._released:
            return
        self._released = True
        self.stop_event.set()
        thread = self._thread
        if thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15.0)
            if thread.is_alive():
                self.logger.warning(
                    "RTSP pump still running after stop; waiting for in-flight grab before release"
                )
        cap = self._take_cap()
        self._close_cap(cap)
        with self._lock:
            self._frame = None
