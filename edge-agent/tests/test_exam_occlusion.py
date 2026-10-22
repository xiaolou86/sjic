"""混合任务里的摄像头遮挡不走检测框，也不吃任务置信度。"""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.exam_pipeline import ExamPipelineAlgorithm


class _Frames:
    def __init__(self, frame):
        self.frame = frame

    def read(self):
        return True, self.frame.copy()

    def isOpened(self):
        return True

    def release(self):
        pass

    def get(self, _prop):
        return 0


class _Runtime:
    def __init__(self):
        self.confs = []

    def load(self, _path):
        return None

    def infer(self, _processed, conf=0.5, classes=None, imgsz=640):
        self.confs.append(conf)
        return type('Result', (), {'boxes': []})()

    def release(self):
        return None


class _Log:
    def __init__(self):
        self.lines = []

    def _keep(self, level, message, args):
        text = message % args if args else str(message)
        self.lines.append(f'{level}:{text}')

    def info(self, message, *args, **_kwargs):
        self._keep('info', message, args)

    def warning(self, message, *args, **_kwargs):
        self._keep('warning', message, args)

    def error(self, message, *args, **_kwargs):
        self._keep('error', message, args)

    def debug(self, message, *args, **_kwargs):
        self._keep('debug', message, args)


def _stripes(h, w, period=16):
    gray = np.zeros((h, w), dtype=np.uint8)
    for x in range(w):
        if (x // period) % 2 == 0:
            gray[:, x] = 255
    return np.stack([gray, gray, gray], axis=2)


def _run(frame, timeout):
    runtime = _Runtime()
    alerts = []
    stop_event = threading.Event()
    log = _Log()

    def on_alert(**kwargs):
        alerts.append(kwargs)
        stop_event.set()

    timer = threading.Timer(timeout, stop_event.set)
    timer.daemon = True
    timer.start()
    config = {
        'task_id': 9,
        'architecture': 'x86',
        'camera': {'rtsp_url': 'rtsp://example/cam'},
        'model_local_paths': {'object_detection': 'fake.onnx'},
        'models': {'object_detection': {'algorithm_id': 7}},
        'parameters': {
            'confidence': 0.5,
            'alertThreshold': 10,
            'inferFps': 20,
            'algorithm_parameters': {
                'rules': [
                    {
                        'id': 'occ',
                        'type': 'camera_occlusion',
                        'name': '摄像头遮挡',
                        'enabled': True,
                        'cover_ratio': 0.25,
                        'seconds': 0,
                        'alert_type': 'camera_blocked',
                        'class_ids': [],
                    },
                    {
                        'id': 'phone',
                        'type': 'presence',
                        'name': '手机',
                        'enabled': True,
                        'class_ids': [1],
                        'alert_type': 'phone_detect',
                    },
                ],
            },
        },
    }
    with patch('algorithms.exam_pipeline.create_runtime', return_value=runtime):
        ExamPipelineAlgorithm().process(
            _Frames(frame), config, log, stop_event, on_alert, None,
        )
    timer.cancel()
    return alerts, log, runtime


class TestExamOcclusionIgnoresDetectorConfidence(unittest.TestCase):
    def test_flat_gray_alerts_while_detector_stays_at_task_confidence(self):
        gray = np.full((128, 160, 3), 140, dtype=np.uint8)
        alerts, log, runtime = _run(gray, timeout=6)
        blocked = [item for item in alerts if item.get('alert_type') == 'camera_blocked']
        self.assertEqual(len(blocked), 1, log.lines)
        self.assertEqual(blocked[0]['confidence'], 1.0)
        self.assertEqual(blocked[0]['algorithm_id'], 7)
        self.assertTrue(runtime.confs)
        self.assertTrue(all(conf == 0.5 for conf in runtime.confs))
        self.assertFalse(any(item.get('alert_type') == 'phone_detect' for item in alerts))
        self.assertFalse(any('Unknown detection rule' in line for line in log.lines))

    def test_textured_frame_does_not_alert(self):
        alerts, log, _runtime = _run(_stripes(128, 160), timeout=1.2)
        self.assertFalse(any(item.get('alert_type') == 'camera_blocked' for item in alerts), log.lines)
