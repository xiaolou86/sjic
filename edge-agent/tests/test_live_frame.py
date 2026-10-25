import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import rtsp  # noqa: E402
from utils.rtsp import FramePump, InferPacer  # noqa: E402
from utils.stream import (  # noqa: E402
    RtspCapture,
    _mask_url,
    _rtspsrc,
    _split_rtsp_auth,
    drain_to_live,
    raw_to_bgr,
)

URL = "rtsp://127.0.0.1/live"


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def _index(frame):
    return int(frame[0, 0, 0]) | (int(frame[0, 0, 1]) << 8)


class _LiveCap:
    """FFmpeg 式直播源：buffered 帧已在缓冲里立刻 grab 到，之后每帧要等 gap 秒才到。

    limit 次之后 grab 失败。retrieve 交出最近一次 grab 的帧，帧号写在左上角像素里。
    """

    def __init__(self, gap=0.02, buffered=0, limit=None):
        self.gap = gap
        self.buffered = buffered
        self.limit = limit
        self.grabs = 0
        self.retrieves = 0
        self.released = False

    def grab(self):
        if self.limit is not None and self.grabs >= self.limit:
            return False
        if self.buffered > 0:
            self.buffered -= 1
        else:
            time.sleep(self.gap)
        self.grabs += 1
        return True

    def retrieve(self):
        self.retrieves += 1
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        frame[0, 0, 0] = self.grabs & 0xFF
        frame[0, 0, 1] = (self.grabs >> 8) & 0xFF
        return True, frame

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def set(self, prop, value):
        return False

    def get(self, prop):
        return 0

    def isOpened(self):
        return not self.released

    def release(self):
        self.released = True


class _LatestCap:
    """GStreamer 式：read 交出 appsink 里最新的一帧，不允许 grab/retrieve。"""

    reads_latest = True

    def __init__(self, ok=True):
        self.ok = ok
        self.reads = 0
        self.timeouts = []
        self.released = False

    def read(self, timeout=None):
        self.reads += 1
        self.timeouts.append(timeout)
        if not self.ok:
            return False, None
        return True, np.full((16, 16, 3), self.reads, dtype=np.uint8)

    def grab(self):
        raise AssertionError("reads_latest source must not be grabbed")

    def retrieve(self):
        raise AssertionError("reads_latest source must not be retrieved")

    def isOpened(self):
        return not self.released

    def release(self):
        self.released = True


class _ReadOnly:
    def read(self):
        return True, np.zeros((16, 16, 3), dtype=np.uint8)

    def isOpened(self):
        return True

    def release(self):
        pass


class TestRtspAuthInPipeline(unittest.TestCase):
    def test_password_may_contain_at(self):
        url = "rtsp://admin:c@111@192.168.25.115:554/Streaming/Channels/101"
        location, username, password = _split_rtsp_auth(url)
        self.assertEqual(location, "rtsp://192.168.25.115:554/Streaming/Channels/101")
        self.assertEqual(username, "admin")
        self.assertEqual(password, "c@111")
        src = _rtspsrc(url)
        self.assertIn('location="rtsp://192.168.25.115:554/Streaming/Channels/101"', src)
        self.assertIn('user-id="admin"', src)
        self.assertIn('user-pw="c@111"', src)
        self.assertNotIn("admin:c", src)
        self.assertNotIn("c@111@", _mask_url(url))

    def test_percent_encoded_password_is_decoded_for_rtspsrc(self):
        location, username, password = _split_rtsp_auth(
            "rtsp://admin:c%40111@192.168.25.115/live"
        )
        self.assertEqual((location, username, password), (
            "rtsp://192.168.25.115/live", "admin", "c@111",
        ))

    def test_quote_in_password_is_escaped(self):
        src = _rtspsrc('rtsp://admin:a"b\\c@192.168.25.115/live')
        self.assertIn(r'user-pw="a\"b\\c"', src)

    def test_url_without_auth_stays_unchanged(self):
        url = "rtsp://192.168.25.115/live"
        self.assertEqual(_split_rtsp_auth(url), (url, "", ""))
        self.assertNotIn("user-id", _rtspsrc(url))
        self.assertEqual(_mask_url(url), url)


class TestDrainToLive(unittest.TestCase):
    def test_stops_at_the_first_frame_that_had_to_wait(self):
        cap = _LiveCap(gap=0.05, buffered=4)
        self.assertEqual(drain_to_live(cap, 0.04), 5)
        self.assertEqual(cap.grabs, 5)

    def test_stops_on_failed_grab(self):
        cap = _LiveCap(gap=0.0, buffered=3, limit=3)
        self.assertEqual(drain_to_live(cap, 0.04), 3)

    def test_none_capture(self):
        self.assertEqual(drain_to_live(None, 0.04), 0)


class TestRtspCaptureRead(unittest.TestCase):
    def _capture(self, fake, backend):
        cap = RtspCapture(URL)
        cap._cap = fake
        cap.backend = backend
        cap.reads_latest = backend.startswith("gstreamer")
        return cap

    def test_ffmpeg_read_returns_the_live_frame_not_the_backlog(self):
        fake = _LiveCap(gap=0.05, buffered=4)
        cap = self._capture(fake, "ffmpeg")
        ok, frame = cap.read()
        self.assertTrue(ok)
        self.assertEqual(_index(frame), 5)
        self.assertEqual(fake.retrieves, 1)

    def test_gstreamer_read_takes_the_newest_sample_directly(self):
        fake = _LatestCap()
        cap = self._capture(fake, "gstreamer-nvdec-h264")
        ok, frame = cap.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (16, 16, 3))
        self.assertEqual(fake.reads, 1)
        self.assertIsNotNone(fake.timeouts[0])


class _FakeClock:
    """stop_event.wait 每次都多睡 oversleep 秒，模拟定时器粒度。"""

    def __init__(self, oversleep):
        self.now = 100.0
        self.oversleep = oversleep
        self.waits = []

    def perf_counter(self):
        return self.now

    def wait(self, timeout):
        self.waits.append(timeout)
        self.now += timeout + self.oversleep
        return False

    def is_set(self):
        return False


class TestInferPacer(unittest.TestCase):
    def test_waits_out_the_rest_of_the_interval(self):
        stop = threading.Event()
        pacer = InferPacer(20)
        started = time.perf_counter()
        for _ in range(6):
            self.assertTrue(pacer.wait(stop))
        elapsed = time.perf_counter() - started
        self.assertGreaterEqual(elapsed, 0.24)
        self.assertLess(elapsed, 0.40)

    def test_slow_inference_starts_next_round_at_once_without_catching_up(self):
        stop = threading.Event()
        pacer = InferPacer(20)
        pacer.wait(stop)
        time.sleep(0.2)
        t0 = time.perf_counter()
        pacer.wait(stop)
        self.assertLess(time.perf_counter() - t0, 0.02)
        t1 = time.perf_counter()
        pacer.wait(stop)
        self.assertGreaterEqual(time.perf_counter() - t1, 0.035)

    def test_timer_oversleep_does_not_accumulate(self):
        clock = _FakeClock(oversleep=0.015)
        with mock.patch.object(rtsp, "time", clock):
            pacer = InferPacer(5)
            starts = []
            for _ in range(11):
                self.assertTrue(pacer.wait(clock))
                starts.append(clock.now)
        self.assertAlmostEqual(starts[-1] - starts[0], 2.0 + 0.015, places=6)

    def test_stop_interrupts_the_wait(self):
        stop = threading.Event()
        pacer = InferPacer(1)
        pacer.wait(stop)
        threading.Timer(0.05, stop.set).start()
        t0 = time.perf_counter()
        self.assertFalse(pacer.wait(stop))
        self.assertLess(time.perf_counter() - t0, 0.5)

    def test_zero_or_bad_fps_does_not_wait(self):
        stop = threading.Event()
        for fps in (0, None, "x", -1):
            pacer = InferPacer(fps)
            t0 = time.perf_counter()
            for _ in range(5):
                self.assertTrue(pacer.wait(stop))
            self.assertLess(time.perf_counter() - t0, 0.05)


class TestFramePumpLive(unittest.TestCase):
    def _pump(self, cap, **kwargs):
        stop = threading.Event()
        pump = FramePump(cap, stop, URL, _Log(), **kwargs)
        pump.start()
        self.addCleanup(pump.release)
        return pump

    def test_decodes_continuously_but_converts_only_on_request(self):
        cap = _LiveCap(gap=0.01)
        pump = self._pump(cap)
        time.sleep(0.3)
        self.assertGreater(cap.grabs, 5)
        self.assertEqual(cap.retrieves, 0)
        frame, seq = pump.get_latest(last_seq=0, wait_sec=1.0)
        self.assertIsNotNone(frame)
        self.assertGreater(seq, 0)
        self.assertLessEqual(cap.retrieves, 2)

    def test_returns_the_newest_frame_at_request_time(self):
        cap = _LiveCap(gap=0.02)
        pump = self._pump(cap)
        time.sleep(0.15)
        seq = 0
        for _ in range(3):
            newest = cap.grabs
            frame, new_seq = pump.get_latest(last_seq=seq, wait_sec=1.0)
            self.assertIsNotNone(frame)
            self.assertGreater(new_seq, seq)
            self.assertGreaterEqual(_index(frame), newest)
            seq = new_seq
            time.sleep(0.05)

    def test_paced_loop_takes_current_frames_at_infer_fps(self):
        cap = _LiveCap(gap=0.02)
        pump = self._pump(cap)
        stop = threading.Event()
        pacer = InferPacer(10)
        seq = 0
        taken = []
        started = time.perf_counter()
        while pacer.wait(stop) and time.perf_counter() - started < 1.0:
            newest = cap.grabs
            frame, seq = pump.get_latest(last_seq=seq, wait_sec=1.0)
            self.assertIsNotNone(frame)
            taken.append((newest, _index(frame)))
            time.sleep(0.03)
        self.assertGreaterEqual(len(taken), 9)
        self.assertLessEqual(len(taken), 11)
        for newest, n in taken:
            self.assertGreaterEqual(n, newest)
        self.assertLessEqual(cap.retrieves, len(taken) + 2)
        self.assertGreater(cap.grabs, 2 * len(taken))

    def test_reconnects_after_repeated_failures(self):
        bad = _LiveCap(gap=0.0, limit=0)
        good = _LiveCap(gap=0.01)
        opened = []

        def open_fn(url):
            opened.append(url)
            return good

        with mock.patch.object(rtsp, "_RECONNECT_FAILS", 3), \
                mock.patch.object(rtsp, "_RECONNECT_DELAY_SEC", 0.01):
            pump = self._pump(bad, open_fn=open_fn)
            frame, _ = pump.get_latest(last_seq=0, wait_sec=2.0)
            pump.release()
        self.assertIsNotNone(frame)
        self.assertEqual(opened, [URL])
        self.assertTrue(bad.released)
        self.assertTrue(good.released)

    def test_release_stops_the_thread_and_closes_the_capture(self):
        cap = _LiveCap(gap=0.01)
        pump = self._pump(cap)
        time.sleep(0.05)
        pump.release()
        self.assertFalse(pump._thread.is_alive())
        self.assertTrue(cap.released)
        self.assertTrue(pump.stop_event.is_set())
        self.assertEqual(pump.get_latest(last_seq=0, wait_sec=0.1), (None, 0))


class TestFramePumpDirect(unittest.TestCase):
    def test_reads_latest_source_is_read_on_demand_without_a_thread(self):
        cap = _LatestCap()
        stop = threading.Event()
        pump = FramePump(cap, stop, URL, _Log())
        pump.start()
        self.assertIsNone(pump._thread)
        time.sleep(0.05)
        self.assertEqual(cap.reads, 0)
        f1, s1 = pump.get_latest(last_seq=0, wait_sec=1.0)
        f2, s2 = pump.get_latest(last_seq=s1, wait_sec=1.0)
        self.assertIsNotNone(f1)
        self.assertIsNotNone(f2)
        self.assertGreater(s2, s1)
        self.assertEqual(cap.reads, 2)
        pump.release()
        self.assertTrue(cap.released)

    def test_read_only_source_uses_direct_mode(self):
        pump = FramePump(_ReadOnly(), threading.Event(), URL, _Log())
        self.assertIsNone(pump._thread)
        frame, seq = pump.get_latest(last_seq=0, wait_sec=0.5)
        self.assertIsNotNone(frame)
        self.assertEqual(seq, 1)

    def test_gives_up_after_wait_sec(self):
        cap = _LatestCap(ok=False)
        pump = FramePump(cap, threading.Event(), URL, _Log())
        t0 = time.perf_counter()
        self.assertEqual(pump.get_latest(last_seq=7, wait_sec=0.1), (None, 7))
        self.assertLess(time.perf_counter() - t0, 0.5)
        pump.release()


def _bgr(width, height):
    rng = np.random.default_rng(width * 1000 + height)
    return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)


def _i420(bgr):
    h, w = bgr.shape[:2]
    flat = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420).reshape(-1)
    y = flat[:w * h].reshape(h, w)
    u = flat[w * h:w * h * 5 // 4].reshape(h // 2, w // 2)
    v = flat[w * h * 5 // 4:].reshape(h // 2, w // 2)
    return y, u, v


def _pad(plane, stride, rows):
    out = np.zeros((rows, stride), dtype=np.uint8)
    out[:plane.shape[0], :plane.shape[1]] = plane
    return out.tobytes()


class TestRawToBgr(unittest.TestCase):
    def test_bgrx_drops_alpha_and_row_padding(self):
        bgr = _bgr(10, 4)
        bgrx = np.dstack([bgr, np.full((4, 10), 255, np.uint8)])
        padded = _pad(bgrx.reshape(4, 40), 48, 4)
        np.testing.assert_array_equal(raw_to_bgr(padded, "BGRx", 10, 4), bgr)

    def test_bgr_with_four_byte_row_alignment(self):
        bgr = _bgr(10, 4)
        padded = _pad(bgr.reshape(4, 30), 32, 4)
        out = raw_to_bgr(padded, "BGR", 10, 4)
        np.testing.assert_array_equal(out, bgr)
        self.assertTrue(out.flags.writeable)

    def test_tight_i420(self):
        bgr = _bgr(20, 10)
        y, u, v = _i420(bgr)
        data = y.tobytes() + u.tobytes() + v.tobytes()
        expected = cv2.cvtColor(np.frombuffer(data, np.uint8).reshape(15, 20), cv2.COLOR_YUV2BGR_I420)
        np.testing.assert_array_equal(raw_to_bgr(data, "I420", 20, 10), expected)

    def test_i420_with_padded_chroma_rows(self):
        bgr = _bgr(20, 10)
        y, u, v = _i420(bgr)
        tight = y.tobytes() + u.tobytes() + v.tobytes()
        padded = _pad(y, 20, 10) + _pad(u, 12, 5) + _pad(v, 12, 5)
        expected = cv2.cvtColor(np.frombuffer(tight, np.uint8).reshape(15, 20), cv2.COLOR_YUV2BGR_I420)
        np.testing.assert_array_equal(raw_to_bgr(padded, "I420", 20, 10), expected)

    def test_nv12_with_decoder_pitch_and_height_padding(self):
        bgr = _bgr(20, 10)
        y, u, v = _i420(bgr)
        uv = np.empty((5, 20), dtype=np.uint8)
        uv[:, 0::2] = u
        uv[:, 1::2] = v
        tight = np.frombuffer(y.tobytes() + uv.tobytes(), np.uint8).reshape(15, 20)
        padded = _pad(y, 32, 16) + _pad(uv, 32, 8)
        expected = cv2.cvtColor(tight, cv2.COLOR_YUV2BGR_NV12)
        np.testing.assert_array_equal(raw_to_bgr(padded, "NV12", 20, 10), expected)

    def test_rejects_size_that_does_not_fit(self):
        with self.assertRaises(ValueError):
            raw_to_bgr(b"\x00" * 7, "BGRx", 10, 4)
        with self.assertRaises(ValueError):
            raw_to_bgr(b"\x00" * 7, "I420", 20, 10)


if __name__ == "__main__":
    unittest.main()
