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
        self.open_fn = open_fn or open_capture
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._fail = 0
        self._thread = threading.Thread(target=self._loop, name='rtsp-pump', daemon=True)

    def start(self):
        self._thread.start()

    def _store(self, frame):
        with self._lock:
            self._frame = frame
            self._seq += 1
            self._fail = 0

    def _reconnect(self):
        self.logger.warning("RTSP pump reconnecting...")
        try:
            self.cap.release()
        except Exception:
            pass
        time.sleep(2)
        cap = self.open_fn(self.url)
        if cap is None or not cap.isOpened():
            self.logger.error("RTSP pump reconnect failed")
            time.sleep(3)
            return
        self.cap = cap
        self._fail = 0
        self.logger.info("RTSP pump reconnected")

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                if self.cap is None or not self.cap.grab():
                    self._fail += 1
                    if self._fail >= 30:
                        self._reconnect()
                    else:
                        time.sleep(0.03)
                    continue
                ret, frame = self.cap.retrieve()
                if ret and is_valid_frame(frame):
                    self._store(frame)
                else:
                    self._fail += 1
            except Exception as e:
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

    def release(self):
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
