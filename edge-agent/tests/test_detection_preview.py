"""预览把超过阈值的候选画出来，不看告警骨骼开关。"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.base import set_show_pose_skeleton
from algorithms.detection_preview import (
    compose_preview,
    configure_preview,
    offer_detection_preview,
    set_preview,
)


class _Box:
    def __init__(self, class_id, confidence, x1=10, y1=10, x2=40, y2=40):
        self.class_id = class_id
        self.confidence = confidence
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


def _shoulders():
    kps = [[0.0, 0.0, 0.0] for _ in range(17)]
    kps[5] = [8.0, 40.0, 1.0]
    kps[6] = [56.0, 40.0, 1.0]
    return kps


class TestComposePreview(unittest.TestCase):
    def tearDown(self):
        set_show_pose_skeleton(False)

    def test_draws_boxes_and_counts_classes(self):
        set_show_pose_skeleton(False)
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        vis, stats = compose_preview(
            frame,
            boxes=[
                _Box(1, 0.91),
                _Box(1, 0.60, x1=12, y1=12, x2=30, y2=30),
                _Box(2, 0.40, x1=50, y1=50, x2=70, y2=70),
            ],
            labelmap={1: '手机', 2: '书'},
            object_threshold=0.35,
        )
        self.assertTrue(np.any(np.all(vis == (0, 255, 0), axis=2)))
        self.assertEqual(stats['object']['count'], 3)
        self.assertEqual(stats['object']['threshold'], 0.35)
        self.assertEqual(stats['object']['classes'][0]['name'], '手机')
        self.assertEqual(stats['object']['classes'][0]['count'], 2)
        self.assertEqual(stats['object']['classes'][0]['max_confidence'], 0.91)
        self.assertEqual(stats['object']['classes'][1]['name'], '书')

    def test_draws_skeleton_even_when_alert_overlay_hides_it(self):
        set_show_pose_skeleton(False)
        frame = np.zeros((80, 96, 3), dtype=np.uint8)
        vis, stats = compose_preview(
            frame,
            persons=[
                (_Box(0, 0.88, x1=4, y1=8, x2=60, y2=70), _shoulders()),
                (_Box(0, 0.50, x1=4, y1=8, x2=20, y2=20), None),
            ],
            pose_threshold=0.4,
        )
        self.assertGreater(int(vis[:, :, 0].max()), 0)
        self.assertEqual(stats['pose']['count'], 2)
        self.assertEqual(stats['pose']['with_skeleton'], 1)
        self.assertTrue(stats['pose']['ok'])
        person = stats['pose']['people'][0]
        self.assertEqual(len(person['points']), 17)
        self.assertTrue(person['points'][5]['ok'])
        self.assertEqual(person['points'][5]['name'], '左肩')
        self.assertIn('鼻', person['missing'])
        self.assertEqual(stats['pose']['people'][1]['usable'], 0)

    def test_occlusion_ratio_is_separate_from_object_threshold(self):
        frame = np.zeros((40, 40, 3), dtype=np.uint8)
        _vis, stats = compose_preview(
            frame,
            boxes=[],
            object_threshold=0.5,
            occlusion={
                'ratio': 0.766,
                'cover_ratio': 0.25,
                'hit': True,
                'seconds': 3,
                'held': 1.2,
            },
        )
        self.assertEqual(stats['object']['count'], 0)
        self.assertEqual(stats['object']['threshold'], 0.5)
        self.assertEqual(stats['occlusion']['ratio'], 0.766)
        self.assertTrue(stats['occlusion']['hit'])

    def test_infer_error_does_not_draw_stale_boxes(self):
        frame = np.zeros((40, 40, 3), dtype=np.uint8)
        vis, stats = compose_preview(
            frame,
            boxes=[_Box(1, 0.99)],
            object_error=True,
            object_threshold=0.5,
        )
        self.assertFalse(np.any(np.all(vis == (0, 255, 0), axis=2)))
        self.assertFalse(stats['object']['ok'])
        self.assertEqual(stats['object']['count'], 0)


class TestOfferGate(unittest.TestCase):
    def tearDown(self):
        set_preview(7, False)

    def test_skips_until_preview_is_on(self):
        configure_preview('http://127.0.0.1/api/edge')
        sunk = []

        def collect(url, jpeg, stats):
            sunk.append((url, jpeg, stats))

        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        offer_detection_preview(7, frame, boxes=[_Box(0, 0.8)], object_threshold=0.5, _sink=collect)
        self.assertEqual(sunk, [])
        set_preview(7, True, labelmap=[{'id': 0, 'name': '手机'}], ttl=30)
        offer_detection_preview(7, frame, boxes=[_Box(0, 0.8)], object_threshold=0.5, _sink=collect)
        offer_detection_preview(7, frame, boxes=[_Box(0, 0.8)], object_threshold=0.5, _sink=collect)
        self.assertEqual(len(sunk), 1)
        url, jpeg, stats = sunk[0]
        self.assertEqual(url, 'http://127.0.0.1/api/edge/tasks/7/preview')
        self.assertTrue(jpeg.startswith(b'\xff\xd8'))
        self.assertEqual(stats['object']['classes'][0]['name'], '手机')


if __name__ == '__main__':
    unittest.main()
