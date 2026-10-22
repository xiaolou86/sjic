"""识别眼镜、识别手表是出现判定。框沾到区域即可，不要求脚点落在里面。"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.rules import PresenceRule, explain_detection_rules


class _Box:
    def __init__(self, x1, y1, x2, y2, class_id, confidence=0.9):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.class_id = class_id
        self.confidence = confidence

    @property
    def foot_center(self):
        return ((self.x1 + self.x2) / 2.0, self.y2)


class _Rect:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def contains(self, point):
        x = getattr(point, 'x', None)
        y = getattr(point, 'y', None)
        if x is None or y is None:
            xy = point.xy
            if len(xy) == 2 and not hasattr(xy[0], '__iter__'):
                x, y = xy
            else:
                x, y = float(xy[0][0]), float(xy[1][0])
        return self.x1 <= float(x) <= self.x2 and self.y1 <= float(y) <= self.y2


class _Log:
    def info(self, *_args, **_kwargs):
        return None


def _glasses_rule():
    rule = PresenceRule(
        {
            'id': 'glasses',
            'type': 'presence',
            'name': '识别眼镜',
            'alert_type': 'glasses_detect',
            'class_ids': [3],
            '_min_confidence': 0.4,
        },
        None,
        10,
    )
    rule._roi_polygon = _Rect(0, 0, 100, 80)
    return rule


class PresenceOverlapTest(unittest.TestCase):
    def test_box_touching_the_region_alerts_even_if_the_foot_is_outside(self):
        rule = _glasses_rule()
        box = _Box(10, 10, 40, 120, class_id=3)
        self.assertGreater(box.foot_center[1], 80)
        now = datetime(2026, 10, 22, 22, 9, 0)
        hit = rule.evaluate([box], now, _Log())
        self.assertIsNotNone(hit)
        self.assertEqual(hit['alert_type'], 'glasses_detect')

    def test_box_fully_outside_or_wrong_class_does_not_alert(self):
        rule = _glasses_rule()
        now = datetime(2026, 10, 22, 22, 9, 0)
        outside = _Box(200, 200, 240, 240, class_id=3)
        wrong = _Box(10, 10, 40, 40, class_id=0)
        low = _Box(10, 10, 40, 40, class_id=3, confidence=0.1)
        self.assertIsNone(rule.evaluate([outside, wrong, low], now, _Log()))

    def test_explain_names_the_missing_class_without_using_cooldown(self):
        rule = _glasses_rule()
        now = datetime(2026, 10, 22, 22, 9, 0)
        rows = explain_detection_rules([rule], [], now)
        self.assertIn('已调用出现判定', rows[0]['people'][0]['reason'])
        self.assertIn('类别 3', rows[0]['people'][0]['reason'])
        self.assertFalse(rows[0]['people'][0]['hit'])
        box = _Box(10, 10, 40, 40, class_id=3)
        hit = rule.evaluate([box], now, _Log())
        self.assertIsNotNone(hit)
