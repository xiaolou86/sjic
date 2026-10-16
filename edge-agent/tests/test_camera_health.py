"""摄像头遮挡只统计最外一圈格子。近黑和发灰的平坦遮挡都算，不要求像素为 0。"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'algorithms'))

from occlusion import DEFAULT_COVER_RATIO, ring_occlusion_ratio, update_occlusion


def _bgr(gray):
    return np.stack([gray, gray, gray], axis=2)


def _stripes(h, w, period=16):
    gray = np.zeros((h, w), dtype=np.uint8)
    for x in range(w):
        if (x // period) % 2 == 0:
            gray[:, x] = 255
    return gray


class TestRingOcclusion(unittest.TestCase):
    def test_near_black_is_occluded_without_being_zero(self):
        rng = np.random.default_rng(1)
        gray = np.full((128, 160), 16, dtype=np.int16)
        gray += rng.integers(-2, 3, size=gray.shape)
        gray = np.clip(gray, 1, 255).astype(np.uint8)
        self.assertGreater(int(gray.min()), 0)
        self.assertGreaterEqual(ring_occlusion_ratio(_bgr(gray)), DEFAULT_COVER_RATIO)

    def test_flat_gray_cover_counts(self):
        gray = np.full((128, 160), 140, dtype=np.uint8)
        self.assertAlmostEqual(ring_occlusion_ratio(_bgr(gray)), 1.0)

    def test_textured_frame_is_clear(self):
        ratio = ring_occlusion_ratio(_bgr(_stripes(128, 160)))
        self.assertLess(ratio, DEFAULT_COVER_RATIO)

    def test_center_cover_does_not_count(self):
        gray = _stripes(128, 160)
        gray[32:96, 32:128] = 30
        self.assertLess(ring_occlusion_ratio(_bgr(gray)), DEFAULT_COVER_RATIO)

    def test_edge_cover_counts(self):
        gray = _stripes(128, 160)
        gray[:, :48] = 90
        self.assertGreaterEqual(ring_occlusion_ratio(_bgr(gray)), DEFAULT_COVER_RATIO)


class TestOcclusionHold(unittest.TestCase):
    def test_alerts_after_hold_and_clears_when_texture_returns(self):
        spec = {'cover_ratio': 0.25, 'seconds': 3}
        state = {}
        flat = np.full((128, 160, 3), 20, dtype=np.uint8)
        start = datetime(2026, 10, 16, 9, 0, 0)
        self.assertIsNone(update_occlusion(spec, flat, start, state, 10))
        self.assertIsNone(update_occlusion(spec, flat, start + timedelta(seconds=2), state, 10))
        message = update_occlusion(spec, flat, start + timedelta(seconds=3), state, 10)
        self.assertIn('摄像头遮挡', message)

        textured = _bgr(_stripes(128, 160))
        self.assertIsNone(update_occlusion(spec, textured, start + timedelta(seconds=4), state, 10))
        self.assertIsNone(state.get('since'))
