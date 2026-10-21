import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.rtsp import FramePump  # noqa: E402
from utils.stream import RtspCapture, discard_arrived_frames  # noqa: E402


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _BufferedCap:
    """前 buffered 次 grab 立刻成功，之后按超时失败，不再往下读。"""

    def __init__(self, buffered):
        self.buffered = buffered
        self.timeout = 2000
        self.grabs = 0
        self.retrieves = 0

    def set(self, prop, value):
        self.timeout = int(value)
        return True

    def grab(self):
        self.grabs += 1
        if self.buffered > 0:
            self.buffered -= 1
            return True
        return False

    def retrieve(self):
        self.retrieves += 1
        return True, np.zeros((16, 16, 3), dtype=np.uint8)


class _SlowCap:
    def __init__(self):
        self.n = 0
        self.timeout = 2000

    def set(self, prop, value):
        self.timeout = int(value)
        return False

    def grab(self):
        self.n += 1
        if self.n > 1:
            time.sleep(0.4)
        return True


class _PumpCap:
    def __init__(self):
        self.reads = 0
        self.grabs = 0

    def read(self):
        self.reads += 1
        return True, np.zeros((16, 16, 3), dtype=np.uint8)

    def grab(self):
        self.grabs += 1
        return True

    def retrieve(self):
        return True, np.zeros((16, 16, 3), dtype=np.uint8)

    def isOpened(self):
        return True

    def release(self):
        pass


class TestDiscardArrivedFrames(unittest.TestCase):
    def test_stops_when_buffer_is_empty(self):
        cap = _BufferedCap(4)
        taken = discard_arrived_frames(cap)
        self.assertEqual(taken, 4)
        self.assertEqual(cap.grabs, 5)
        self.assertEqual(cap.timeout, 2000)

    def test_empty_buffer_does_not_wait_for_the_next_frame(self):
        cap = _BufferedCap(0)
        taken = discard_arrived_frames(cap)
        self.assertEqual(taken, 0)
        self.assertEqual(cap.grabs, 1)

    def test_slow_grab_stops_the_drain(self):
        cap = _SlowCap()
        taken = discard_arrived_frames(cap)
        self.assertEqual(taken, 2)
        self.assertEqual(cap.n, 2)


class TestRtspCaptureLatest(unittest.TestCase):
    def _capture(self, backend, buffered):
        cap = RtspCapture("rtsp://127.0.0.1/live")
        fake = _BufferedCap(buffered)
        cap._cap = fake
        cap._backend = backend
        return cap, fake

    def test_gstreamer_reads_one_frame(self):
        cap, fake = self._capture("gstreamer-cpu-h264", 8)
        ok, frame = cap.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape[0], 16)
        self.assertEqual(fake.grabs, 1)
        self.assertEqual(fake.retrieves, 1)

    def test_ffmpeg_keeps_only_the_newest_buffered_frame(self):
        cap, fake = self._capture("ffmpeg", 4)
        ok, _frame = cap.read()
        self.assertTrue(ok)
        self.assertEqual(fake.grabs, 5)
        self.assertEqual(fake.retrieves, 1)


class TestFramePumpSkipsIdle(unittest.TestCase):
    def test_interval_does_not_grab(self):
        cap = _PumpCap()
        stop = threading.Event()
        pump = FramePump(cap, stop, "rtsp://127.0.0.1/live", _Log(), max_decode_fps=2.0)
        pump.start()
        time.sleep(0.35)
        pump.release()
        self.assertGreaterEqual(cap.reads, 1)
        self.assertLessEqual(cap.reads, 2)
        self.assertEqual(cap.grabs, 0)


if __name__ == "__main__":
    unittest.main()
