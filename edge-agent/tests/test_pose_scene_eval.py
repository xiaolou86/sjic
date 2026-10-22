"""姿态场景的计时和冷却只在 PoseBehaviorAlgorithm.evaluate_behaviors 里做一次。"""
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# 判定测试不画图。缺 cv2 / numpy / shapely 时用空模块把包导入撑过去。
if 'cv2' not in sys.modules:
    sys.modules['cv2'] = types.ModuleType('cv2')
if 'numpy' not in sys.modules:
    numpy_mod = types.ModuleType('numpy')
    numpy_mod.ndarray = type('ndarray', (), {})
    sys.modules['numpy'] = numpy_mod
if 'shapely.geometry' not in sys.modules:
    shapely_mod = types.ModuleType('shapely')
    geometry_mod = types.ModuleType('shapely.geometry')

    class _Point:
        def __init__(self, xy):
            self.xy = xy

    class _Polygon:
        def __init__(self, points):
            self.points = points

        def contains(self, _point):
            return True

    geometry_mod.Point = _Point
    geometry_mod.Polygon = _Polygon
    geometry_mod.LineString = _Polygon
    shapely_mod.geometry = geometry_mod
    sys.modules['shapely'] = shapely_mod
    sys.modules['shapely.geometry'] = geometry_mod

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.pose_behavior import PersonTracker, PoseBehaviorAlgorithm
from algorithms.pose_geometry import is_desk_standing, is_finger_point


class _Box:
    def __init__(self, confidence=0.9, x1=10, y1=10, x2=50, y2=90):
        self.confidence = confidence
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2


def _blank_kps():
    return [[0.0, 0.0, 0.0] for _ in range(17)]


def _desk_pose(box, bent=False):
    """高框里的伸直腿。bent 时两膝向外弯，夹角低于站立阈值。"""
    kps = _blank_kps()
    x1, y1, x2, y2 = float(box.x1), float(box.y1), float(box.x2), float(box.y2)
    mid = (x1 + x2) / 2.0
    half = max((x2 - x1) * 0.22, 6.0)
    height = y2 - y1
    shoulder_y = y1 + height * 0.16
    hip_y = y1 + height * 0.40
    knee_y = y1 + height * 0.66
    ankle_y = y1 + height * 0.90
    knee_shift = half * 2.4 if bent else half * 0.05

    def put(index, x, y):
        kps[index] = [x, y, 0.9]

    put(5, mid - half, shoulder_y)
    put(6, mid + half, shoulder_y)
    put(11, mid - half * 0.45, hip_y)
    put(12, mid + half * 0.45, hip_y)
    put(13, mid - half * 0.45 - knee_shift, knee_y)
    put(14, mid + half * 0.45 + knee_shift, knee_y)
    put(15, mid - half * 0.40, ankle_y)
    put(16, mid + half * 0.40, ankle_y)
    return kps


def _person(cx, half=40, box=None):
    """双肩中点在 cx，肩宽 2*half。box 不传时用一个普通人体框。"""
    kps = _blank_kps()
    kps[5] = [cx - half, 100.0, 0.9]
    kps[6] = [cx + half, 100.0, 0.9]
    if box is None:
        box = _Box(x1=cx - half, y1=40, x2=cx + half, y2=240)
    return (box, kps)


class _Log:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, *_args, **_kwargs):
        return None

    def debug(self, *_args, **_kwargs):
        return None


def _eval(algo, behaviors, persons, now, state, alerts, pose_only=False, algorithm_id=7):
    algo.evaluate_behaviors(
        behaviors,
        persons,
        now,
        'frame',
        'front',
        0.5,
        None,
        None,
        10,
        'task-1',
        state['since'],
        state['last'],
        state['extra'],
        {},
        {},
        lambda **kwargs: alerts.append(kwargs),
        _Log() if 'log' not in state else state['log'],
        algorithm_id=algorithm_id,
        pose_only=pose_only,
    )


class PoseSceneEvalTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'gaze',
            'type': 'gaze_away',
            'name': '张望',
            'seconds': 3,
            'alert_type': 'gaze_away',
        }
        self.box = _Box()
        self.persons = [(self.box, [[0, 0, 1]])]
        self.state = {
            'since': {'gaze': None},
            'last': {'gaze': None},
            'extra': {'gaze': {}},
        }
        self.alerts = []
        self.start = datetime(2026, 1, 1, 8, 0, 0)

    def test_first_hit_starts_timer_then_alerts_once_per_cooldown(self):
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            _eval(self.algo, [self.spec], self.persons, self.start, self.state, self.alerts)
            self.assertEqual(self.alerts, [])
            self.assertEqual(self.algo._person_tracker.tracks[0].since['gaze'], self.start)

            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=2), self.state, self.alerts,
            )
            self.assertEqual(self.alerts, [])

            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=3), self.state, self.alerts,
            )
            self.assertEqual(len(self.alerts), 1)
            self.assertEqual(self.alerts[0]['alert_type'], 'gaze_away')
            self.assertEqual(self.alerts[0]['algorithm_id'], 7)
            self.assertIn('持续 3.0s', self.alerts[0]['message'])

            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=12), self.state, self.alerts,
            )
            self.assertEqual(len(self.alerts), 1)

            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=13), self.state, self.alerts,
            )
        self.assertEqual(len(self.alerts), 2)

    def test_miss_resets_timer(self):
        with patch('algorithms.pose_behavior._eval_behavior', side_effect=[True, False, True]):
            _eval(self.algo, [self.spec], self.persons, self.start, self.state, self.alerts)
            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=1), self.state, self.alerts,
            )
            self.assertNotIn('gaze', self.algo._person_tracker.tracks[0].since)
            _eval(
                self.algo, [self.spec], self.persons,
                self.start + timedelta(seconds=4), self.state, self.alerts,
            )
        self.assertEqual(self.alerts, [])
        self.assertEqual(
            self.algo._person_tracker.tracks[0].since['gaze'],
            self.start + timedelta(seconds=4),
        )

    def test_each_visible_person_is_judged(self):
        seen = []

        def fake(btype, kps, box, spec, view):
            seen.append(kps)
            return False

        with patch('algorithms.pose_behavior._eval_behavior', side_effect=fake):
            _eval(
                self.algo, [self.spec],
                [(self.box, 'first'), (_Box(), 'second')],
                self.start, self.state, self.alerts,
            )
        self.assertEqual(seen, ['first', 'second'])

    def test_pose_only_skips_watch_and_mixed_task_ignores_it(self):
        watch = {'id': 'watch', 'type': 'smart_watch', 'name': '手表'}
        state = {
            'since': {'watch': None},
            'last': {'watch': None},
            'extra': {'watch': {}},
            'log': _Log(),
        }
        _eval(self.algo, [watch], [], self.start, state, self.alerts, pose_only=True)
        _eval(self.algo, [watch], [], self.start, state, self.alerts, pose_only=True)
        self.assertEqual(len(state['log'].warnings), 1)
        self.assertEqual(self.alerts, [])

        quiet = {
            'since': {'watch': None},
            'last': {'watch': None},
            'extra': {'watch': {}},
            'log': _Log(),
        }
        _eval(self.algo, [watch], [], self.start, quiet, self.alerts, pose_only=False)
        self.assertEqual(quiet['log'].warnings, [])


class PerPersonTimingTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'gaze',
            'type': 'gaze_away',
            'name': '张望',
            'seconds': 3,
            'alert_type': 'gaze_away',
        }
        self.start = datetime(2026, 1, 1, 8, 0, 0)
        self.state = {
            'since': {'gaze': None},
            'last': {'gaze': None},
            'extra': {'gaze': {}},
        }
        self.alerts = []

    def _run(self, persons, now, spec=None, pose_only=False, state=None):
        _eval(
            self.algo,
            [spec or self.spec],
            persons,
            now,
            state or self.state,
            self.alerts,
            pose_only=pose_only,
        )

    def test_one_person_then_another_does_not_add_up(self):
        seated_a = _person(100)
        seated_b = _person(500)
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run([seated_a], self.start)
            self._run([seated_a], self.start + timedelta(seconds=2))
            self._run([seated_b], self.start + timedelta(seconds=2.2))
            self._run([seated_b], self.start + timedelta(seconds=4.2))
        self.assertEqual(self.alerts, [])

    def test_each_person_alerts_when_their_own_timer_is_full(self):
        people = [_person(100), _person(500)]
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run(people, self.start)
            self._run(people, self.start + timedelta(seconds=3))
        self.assertEqual(len(self.alerts), 2)
        self.assertEqual(len(self.algo._person_tracker.tracks), 2)

    def test_one_alert_does_not_block_the_other_person(self):
        seated_a = _person(100)
        seated_b = _person(500)
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run([seated_a], self.start)
            self._run([seated_a], self.start + timedelta(seconds=2))
            self._run([seated_a, seated_b], self.start + timedelta(seconds=3))
            self._run([seated_a, seated_b], self.start + timedelta(seconds=6))
        self.assertEqual(len(self.alerts), 2)

    def test_two_missed_frames_at_one_fps_keep_the_timer(self):
        seated = _person(200)
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run([seated], self.start)
            self._run([seated], self.start + timedelta(seconds=1))
            track_id = self.algo._person_tracker.tracks[0].id
            self._run([], self.start + timedelta(seconds=2))
            self._run([], self.start + timedelta(seconds=3))
            self.assertEqual(self.algo._person_tracker.tracks[0].id, track_id)
            self._run([seated], self.start + timedelta(seconds=4))
        self.assertEqual(self.algo._person_tracker.tracks[0].id, track_id)
        self.assertEqual(len(self.alerts), 1)
        self.assertIn('持续 4.0s', self.alerts[0]['message'])

    def test_third_missed_frame_starts_a_new_timer(self):
        seated = _person(200)
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run([seated], self.start)
            old_id = self.algo._person_tracker.tracks[0].id
            self._run([], self.start + timedelta(seconds=1))
            self._run([], self.start + timedelta(seconds=2))
            self.assertEqual(self.algo._person_tracker.tracks[0].id, old_id)
            self._run([], self.start + timedelta(seconds=3))
            self.assertEqual(self.algo._person_tracker.tracks, [])
            self._run([seated], self.start + timedelta(seconds=4))
            self.assertNotEqual(self.algo._person_tracker.tracks[0].id, old_id)
            self._run([seated], self.start + timedelta(seconds=6))
        self.assertEqual(self.alerts, [])

    def test_smaller_box_with_the_same_shoulders_is_the_same_person(self):
        wide = _person(100, box=_Box(x1=0, y1=0, x2=200, y2=400))
        small = _person(100, box=_Box(x1=0, y1=0, x2=40, y2=80))
        with patch('algorithms.pose_behavior._eval_behavior', return_value=True):
            self._run([wide], self.start)
            track_id = self.algo._person_tracker.tracks[0].id
            self._run([small], self.start + timedelta(seconds=3))
        self.assertEqual(self.algo._person_tracker.tracks[0].id, track_id)
        self.assertEqual(len(self.alerts), 1)

    def test_tall_neighbor_boxes_are_not_the_same_person(self):
        tracker = PersonTracker()
        now = self.start
        left = _person(100, half=20, box=_Box(x1=80, y1=10, x2=120, y2=210))
        right = _person(150, half=20, box=_Box(x1=130, y1=10, x2=170, y2=210))
        tracker.update([left, right], now)
        ids = [track.id for track in tracker.tracks]
        self.assertEqual(len(ids), 2)
        left_again = _person(100, half=20, box=_Box(x1=80, y1=10, x2=120, y2=210))
        right_again = _person(152, half=20, box=_Box(x1=132, y1=10, x2=172, y2=210))
        tracker.update([left_again, right_again], now + timedelta(seconds=0.2))
        self.assertEqual([track.id for track in tracker.tracks], ids)

    def test_box_center_still_follows_a_person_without_keypoints(self):
        tracker = PersonTracker()
        now = self.start
        tracker.update([(_Box(x1=100, y1=50, x2=180, y2=300), None)], now)
        track_id = tracker.tracks[0].id
        tracker.update([(_Box(x1=108, y1=55, x2=188, y2=305), None)], now + timedelta(seconds=0.2))
        self.assertEqual(tracker.tracks[0].id, track_id)

    def test_glasses_touches_are_counted_per_person(self):
        spec = {
            'id': 'glasses',
            'type': 'smart_glasses',
            'name': '眼镜',
            'min_touches': 2,
            'seconds': 30,
            'alert_type': 'smart_glasses',
        }
        state = {
            'since': {'glasses': None},
            'last': {'glasses': None},
            'extra': {'glasses': {}},
        }
        seated_a = _person(100)
        seated_b = _person(500)
        active = {'ids': set()}

        def wrist(kps, _ratio):
            return id(kps) in active['ids']

        def frame(second, ids):
            active['ids'] = ids
            self._run(
                [seated_a, seated_b],
                self.start + timedelta(seconds=second),
                spec=spec,
                pose_only=True,
                state=state,
            )

        with patch('algorithms.pose_behavior.is_wrist_near_ear', side_effect=wrist):
            frame(0, {id(seated_a[1])})
            frame(1, set())
            frame(2, {id(seated_b[1])})
            self.assertEqual(self.alerts, [])
            frame(3, set())
            frame(4, {id(seated_b[1])})
        self.assertEqual(len(self.alerts), 1)

    def test_watch_fusion_cooldown_is_per_person(self):
        from algorithms.exam_pipeline import ExamPipelineAlgorithm

        pipeline = ExamPipelineAlgorithm()
        pipeline.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        seated_a = _person(100)
        seated_b = _person(500)
        spec = {
            'id': 'watch',
            'type': 'smart_watch',
            'name': '手表',
            'min_touches': 1,
            'seconds': 30,
            'alert_type': 'smart_watch',
        }
        clicking = {'ids': set()}
        log = _Log()
        empty = {'since': {}, 'last': {}, 'extra': {}}

        def click(kps, _boxes, _ratio):
            return id(kps) in clicking['ids']

        def frame(people, second, who):
            now = self.start + timedelta(seconds=second)
            clicking['ids'] = {id(person[1]) for person in who}
            _eval(self.algo, [], people, now, empty, self.alerts)
            with patch('algorithms.pose_behavior.is_finger_click_watch', side_effect=click):
                pipeline._eval_fusions(
                    [spec], [], people, now, 'frame', 0.5,
                    None, None, 10, 'task', 3, {}, {},
                    self.algo, lambda **kwargs: self.alerts.append(kwargs), log,
                )

        frame([seated_a, seated_b], 0, [seated_a])
        frame([seated_a, seated_b], 1, [seated_b])
        self.assertEqual(len(self.alerts), 2)


def _pointing(cx, half=40):
    """站立并向前下方伸右臂。双肩中点在 cx，肩宽 2*half。"""
    kps = _blank_kps()
    kps[5] = [cx - half, 80.0, 0.9]
    kps[6] = [cx + half, 80.0, 0.9]
    kps[8] = [cx + 60, 160.0, 0.9]
    kps[10] = [cx + 50, 250.0, 0.9]
    kps[11] = [cx - 28, 200.0, 0.9]
    kps[12] = [cx + 28, 200.0, 0.9]
    kps[13] = [cx - 26, 300.0, 0.9]
    kps[14] = [cx + 26, 300.0, 0.9]
    kps[15] = [cx - 24, 400.0, 0.9]
    kps[16] = [cx + 24, 400.0, 0.9]
    box = _Box(x1=cx - half, y1=20, x2=cx + half, y2=420)
    return (box, kps)


class FingerPointMotionTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'finger',
            'type': 'finger_point',
            'name': '手指屏幕',
            'seconds': 2,
            'require_standing': True,
            'max_move_ratio': 1.0,
            'alert_type': 'finger_screen',
        }
        self.start = datetime(2026, 1, 1, 8, 0, 0)
        self.state = {
            'since': {'finger': None},
            'last': {'finger': None},
            'extra': {'finger': {}},
        }
        self.alerts = []

    def _run(self, persons, second):
        _eval(
            self.algo, [self.spec], persons,
            self.start + timedelta(seconds=second),
            self.state, self.alerts,
        )

    def test_still_pointing_alerts(self):
        self._run([_pointing(200)], 0)
        self.assertEqual(self.alerts, [])
        self._run([_pointing(230)], 2)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0]['alert_type'], 'finger_screen')
        self.assertIn('持续 2.0s', self.alerts[0]['message'])

    def test_walking_restarts_until_the_person_stays(self):
        # 肩宽 80，匹配门限 60。每步 50 仍是同一人，累计超过 1 倍肩宽则重新计时。
        self._run([_pointing(200)], 0)
        self._run([_pointing(250)], 1)
        self._run([_pointing(300)], 2)
        self.assertEqual(self.alerts, [])
        self.assertIn('路过摆臂', self.algo._person_tracker.tracks[0].hold_note['finger'])
        self._run([_pointing(300)], 3)
        self._run([_pointing(300)], 4)
        self.assertEqual(len(self.alerts), 1)


class DeskStandTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'stand',
            'type': 'desk_stand',
            'name': '考台旁站人',
            'seconds': 5,
            'min_height_width': 1.6,
            'max_move_ratio': 1.0,
            'alert_type': 'desk_stand',
        }
        self.start = datetime(2026, 1, 1, 8, 0, 0)
        self.state = {
            'since': {'stand': None},
            'last': {'stand': None},
            'extra': {'stand': {}},
        }
        self.alerts = []

    def _run(self, persons, second):
        _eval(
            self.algo, [self.spec], persons,
            self.start + timedelta(seconds=second),
            self.state, self.alerts,
        )

    def test_still_tall_box_is_assist_cheat(self):
        still = _Box(x1=100, y1=20, x2=140, y2=180)
        nudged = _Box(x1=108, y1=24, x2=148, y2=184)
        self.assertTrue(is_desk_standing(_desk_pose(still), still, 1.6))
        self._run([(still, _desk_pose(still))], 0)
        self.assertEqual(self.alerts, [])
        self._run([(nudged, _desk_pose(nudged))], 5)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0]['alert_type'], 'desk_stand')
        self.assertIn('辅助作弊', self.alerts[0]['message'])
        self.assertIn('站立不动 5.0s', self.alerts[0]['message'])

    def test_tall_box_without_skeleton_is_skipped(self):
        still = _Box(x1=100, y1=20, x2=140, y2=180)
        self._run([(still, None)], 0)
        self._run([(still, None)], 8)
        self.assertEqual(self.alerts, [])

    def test_bent_knees_stay_quiet(self):
        still = _Box(x1=100, y1=20, x2=140, y2=180)
        pose = _desk_pose(still, bent=True)
        self.assertFalse(is_desk_standing(pose, still, 1.6))
        self._run([(still, pose)], 0)
        self._run([(still, pose)], 8)
        self.assertEqual(self.alerts, [])

    def test_short_box_stays_quiet_even_with_straight_legs(self):
        sitting = _Box(x1=80, y1=80, x2=180, y2=160)
        pose = _desk_pose(sitting)
        self.assertFalse(is_desk_standing(pose, sitting, 1.6))
        self._run([(sitting, pose)], 0)
        self._run([(sitting, pose)], 8)
        self.assertEqual(self.alerts, [])

    def test_walking_restarts_until_the_person_stays(self):
        first = _Box(x1=100, y1=20, x2=140, y2=180)
        walked = _Box(x1=180, y1=20, x2=220, y2=180)
        self._run([(first, _desk_pose(first))], 0)
        self._run([(walked, _desk_pose(walked))], 2)
        self._run([(walked, _desk_pose(walked))], 6)
        self.assertEqual(self.alerts, [])
        self._run([(walked, _desk_pose(walked))], 7)
        self.assertEqual(len(self.alerts), 1)

    def test_a_sitter_does_not_take_the_standers_alert(self):
        stand_box = _Box(x1=100, y1=20, x2=140, y2=180)
        sit_box = _Box(x1=400, y1=80, x2=500, y2=160)
        stand = (stand_box, _desk_pose(stand_box))
        sit = (sit_box, _desk_pose(sit_box))
        self._run([stand, sit], 0)
        self._run([stand, sit], 5)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(len(self.algo._person_tracker.tracks), 2)

    def test_each_still_stander_alerts_on_their_own_track(self):
        left_box = _Box(x1=100, y1=20, x2=140, y2=180)
        right_box = _Box(x1=400, y1=30, x2=450, y2=210)
        left = (left_box, _desk_pose(left_box))
        right = (right_box, _desk_pose(right_box))
        self._run([left, right], 0)
        self._run([left, right], 5)
        self.assertEqual(len(self.alerts), 2)


def _pointing_pose(raised=False):
    kps = _blank_kps()
    elbow = (200, 70) if raised else (230, 150)
    wrist = (210, 40) if raised else (190, 240)
    points = {
        5: (100, 80), 6: (180, 80),
        8: elbow, 10: wrist,
        11: (112, 200), 12: (168, 200),
        13: (114, 300), 14: (166, 300),
        15: (116, 400), 16: (164, 400),
    }
    for index, (x, y) in points.items():
        kps[index] = [float(x), float(y), 0.9]
    return kps


class FingerPointSceneTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'point',
            'type': 'finger_point',
            'name': '手指屏幕',
            'seconds': 1,
            'require_standing': True,
            'alert_type': 'finger_screen',
        }
        self.start = datetime(2026, 1, 1, 8, 0, 0)
        self.state = {
            'since': {'point': None},
            'last': {'point': None},
            'extra': {'point': {}},
        }
        self.alerts = []
        self.box = _Box(x1=60, y1=40, x2=230, y2=430)

    def _run(self, pose, second):
        _eval(
            self.algo, [self.spec], [(self.box, pose)],
            self.start + timedelta(seconds=second),
            self.state, self.alerts,
        )

    def test_forward_reach_while_standing_alerts(self):
        pose = _pointing_pose()
        self.assertTrue(is_finger_point(pose, True, 'back_top', self.box))
        self._run(pose, 0)
        self.assertEqual(self.alerts, [])
        self._run(pose, 1)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0]['alert_type'], 'finger_screen')

    def test_raised_wrist_does_not_alert(self):
        pose = _pointing_pose(raised=True)
        self.assertFalse(is_finger_point(pose, True, 'back_top', self.box))
        self._run(pose, 0)
        self._run(pose, 3)
        self.assertEqual(self.alerts, [])

    def test_sitting_reach_does_not_alert(self):
        pose = _pointing_pose()
        sitting = _Box(x1=60, y1=80, x2=260, y2=200)
        self.assertFalse(is_finger_point(pose, True, 'back_top', sitting))
        _eval(
            self.algo, [self.spec], [(sitting, pose)],
            self.start, self.state, self.alerts,
        )
        _eval(
            self.algo, [self.spec], [(sitting, pose)],
            self.start + timedelta(seconds=3), self.state, self.alerts,
        )
        self.assertEqual(self.alerts, [])


def _turned_standing_pose():
    kps = _blank_kps()
    points = {
        0: (140, 40), 1: (125, 38), 2: (155, 38), 3: (110, 42), 4: (170, 42),
        5: (100, 80), 6: (180, 80),
        11: (112, 200), 12: (168, 200),
        13: (114, 300), 14: (166, 300),
        15: (116, 400), 16: (164, 400),
    }
    for index, (x, y) in points.items():
        kps[index] = [float(x), float(y), 0.9]
    return kps


class GazeAwayStandingGateTest(unittest.TestCase):
    def setUp(self):
        self.algo = PoseBehaviorAlgorithm()
        self.algo.draw_alert_overlay = lambda *args, **kwargs: 'overlay'
        self.spec = {
            'id': 'gaze',
            'type': 'gaze_away',
            'name': '长时间不看屏幕',
            'seconds': 1,
            'alert_type': 'gaze_away',
        }
        self.start = datetime(2026, 1, 1, 8, 0, 0)
        self.state = {
            'since': {'gaze': None},
            'last': {'gaze': None},
            'extra': {'gaze': {}},
        }
        self.alerts = []

    def _run(self, box, second):
        _eval(
            self.algo, [self.spec], [(box, _turned_standing_pose())],
            self.start + timedelta(seconds=second),
            self.state, self.alerts,
        )

    def test_standing_does_not_alert(self):
        standing = _Box(x1=60, y1=40, x2=230, y2=430)
        self._run(standing, 0)
        self._run(standing, 2)
        self.assertEqual(self.alerts, [])

    def test_sitting_alerts(self):
        sitting = _Box(x1=60, y1=80, x2=260, y2=200)
        self._run(sitting, 0)
        self.assertEqual(self.alerts, [])
        self._run(sitting, 1)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0]['alert_type'], 'gaze_away')


class FusionPreviewReasonTest(unittest.TestCase):
    def test_glasses_without_a_person_says_whether_the_box_exists(self):
        algo = PoseBehaviorAlgorithm()
        spec = {
            'id': 'g',
            'type': 'smart_glasses',
            'name': 'AI眼镜',
            'class_ids': [2],
            'min_touches': 3,
        }
        now = datetime(2026, 10, 22, 22, 0, 0)
        empty = algo.preview_debug(
            [spec], [], now, 'back_top', 0.5, None, None, {}, boxes=[],
        )
        self.assertIn('没有眼镜框', empty[0]['reason'])
        self.assertIn('类别 2', empty[0]['reason'])

        glasses = _Box(confidence=0.9, x1=10, y1=10, x2=40, y2=30)
        glasses.class_id = 2
        found = algo.preview_debug(
            [spec], [], now, 'back_top', 0.5, None, None, {}, boxes=[glasses],
        )
        self.assertIn('检出眼镜 1 个', found[0]['reason'])

    def test_still_frame_touch_count_stays_visible(self):
        algo = PoseBehaviorAlgorithm()
        spec = {
            'id': 'g',
            'type': 'smart_glasses',
            'name': 'AI眼镜',
            'class_ids': [2],
            'min_touches': 3,
            '_class_note': '类别 9（眼镜）按模型改到 2（glasses）',
        }
        person = _Box(confidence=0.9, x1=60, y1=40, x2=230, y2=430)
        kps = _turned_standing_pose()
        now = datetime(2026, 10, 22, 22, 0, 0)
        algo._person_tracker.update([(person, kps)], now)
        track = algo._person_tracker.track_for(person, kps)
        track.touch['g'] = {'touches': 1, 'near': True}
        rows = algo.preview_debug(
            [spec], [(person, kps)], now, 'back_top', 0.5, None, None, {}, boxes=[],
        )
        reason = rows[0]['people'][0]['reason']
        self.assertIn('累计 1/3 次', reason)
        self.assertIn('按住中', reason)
        self.assertIn('按模型改到 2', rows[0]['reason'])
