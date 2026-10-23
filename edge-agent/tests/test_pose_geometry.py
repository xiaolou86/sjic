"""Synthetic COCO-17 keypoints covering exam-hall camera views."""
import unittest
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'algorithms'))

from pose_geometry import (
    accumulate_rising_count,
    explain_scene,
    is_cover_mouth,
    is_desk_standing,
    is_finger_point,
    keypoint_debug_rows,
    is_fall,
    is_finger_click_watch,
    person_has_glasses,
    full_face_visible,
    is_gaze_away,
    is_head_down,
    is_head_up,
    is_looking_aside,
    is_standing,
    is_standing_by_box,
    normalize_mount_position,
)

NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16


def kps(**points):
    out = [[0.0, 0.0, 0.0] for _ in range(17)]
    names = {
        'nose': NOSE, 'l_eye': L_EYE, 'r_eye': R_EYE, 'l_ear': L_EAR, 'r_ear': R_EAR,
        'l_shoulder': L_SHOULDER, 'r_shoulder': R_SHOULDER,
        'l_elbow': L_ELBOW, 'r_elbow': R_ELBOW,
        'l_wrist': L_WRIST, 'r_wrist': R_WRIST,
        'l_hip': L_HIP, 'r_hip': R_HIP,
        'l_knee': L_KNEE, 'r_knee': R_KNEE,
        'l_ankle': L_ANKLE, 'r_ankle': R_ANKLE,
    }
    for name, xyz in points.items():
        out[names[name]] = [float(xyz[0]), float(xyz[1]), float(xyz[2])]
    return out


def sitting_torso(**extra):
    base = dict(
        l_shoulder=(100, 200, 0.9),
        r_shoulder=(180, 200, 0.9),
        l_hip=(110, 280, 0.85),
        r_hip=(170, 280, 0.85),
    )
    base.update(extra)
    return kps(**base)


class MountPositionTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_mount_position('front_top'), 'front_top')
        self.assertEqual(normalize_mount_position(''), 'back_top')
        self.assertEqual(normalize_mount_position('unknown'), 'back_top')


class BackTopExamSittingTest(unittest.TestCase):
    """现场图：后上方，考生低头看屏，只见后脑和双耳。"""

    def setUp(self):
        self.kps = sitting_torso(
            l_ear=(115, 155, 0.85),
            r_ear=(165, 155, 0.85),
        )

    def test_normal_look_at_screen_is_not_violation(self):
        self.assertFalse(is_looking_aside(self.kps, view='back_top'))
        self.assertFalse(is_head_down(self.kps, view='back_top'))
        self.assertFalse(is_gaze_away(self.kps, view='back_top'))
        self.assertFalse(is_fall(self.kps, view='back_top'))

    def test_peek_left_is_look_aside(self):
        peek = sitting_torso(
            l_ear=(80, 158, 0.9),
            r_ear=(140, 162, 0.25),
        )
        self.assertTrue(is_looking_aside(peek, view='back_top'))
        self.assertFalse(full_face_visible(peek))
        self.assertFalse(is_gaze_away(peek, view='back_top'))

    def test_turned_around_is_gaze_away_not_look_aside(self):
        face = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(125, 165, 0.85),
            r_eye=(155, 165, 0.85),
            l_ear=(110, 168, 0.6),
            r_ear=(170, 168, 0.6),
        )
        self.assertFalse(is_looking_aside(face, view='back_top'))
        self.assertTrue(is_head_up(face, view='back_top'))
        self.assertTrue(is_gaze_away(face, view='back_top'))

    def test_hunched_at_screen_is_head_down_not_gaze_away(self):
        """伏案看屏只见后脑。这是低头，五个头部点不齐，不算不看屏幕。"""
        hunched = sitting_torso(
            l_ear=(115, 195, 0.85),
            r_ear=(165, 195, 0.85),
        )
        self.assertTrue(is_head_down(hunched, view='back_top'))
        self.assertFalse(is_head_up(hunched, view='back_top'))
        self.assertFalse(is_looking_aside(hunched, view='back_top'))
        self.assertFalse(is_gaze_away(hunched, view='back_top'))

    def test_full_face_is_turned_away(self):
        """后上方五个头部点都在，视为转头，不再看肩线偏移或抬头幅度。"""
        turned = sitting_torso(
            nose=(140, 192, 0.7),
            l_eye=(128, 190, 0.6),
            r_eye=(152, 190, 0.6),
            l_ear=(115, 195, 0.85),
            r_ear=(165, 195, 0.85),
        )
        missing_ear = sitting_torso(
            nose=(140, 192, 0.7),
            l_eye=(128, 190, 0.6),
            r_eye=(152, 190, 0.6),
            l_ear=(115, 195, 0.85),
        )
        low_conf = sitting_torso(
            nose=(140, 192, 0.7),
            l_eye=(128, 190, 0.49),
            r_eye=(152, 190, 0.6),
            l_ear=(115, 195, 0.85),
            r_ear=(165, 195, 0.85),
        )
        self.assertTrue(full_face_visible(turned))
        self.assertTrue(is_gaze_away(turned, view='back_top'))
        self.assertFalse(is_gaze_away(missing_ear, view='back_top'))
        self.assertFalse(is_gaze_away(low_conf, view='back_top'))
        self.assertFalse(is_gaze_away(low_conf, view='side_top'))


class FrontTopTest(unittest.TestCase):
    def test_looking_at_screen_is_not_gaze_away(self):
        """前上方看屏幕：鼻在肩下，这是正常考试，旧逻辑会误报。"""
        screen = sitting_torso(
            nose=(140, 210, 0.9),
            l_eye=(125, 200, 0.85),
            r_eye=(155, 200, 0.85),
            l_ear=(110, 185, 0.8),
            r_ear=(170, 185, 0.8),
        )
        self.assertFalse(is_looking_aside(screen, view='front_top'))
        self.assertFalse(is_head_down(screen, view='front_top'))
        self.assertFalse(is_gaze_away(screen, view='front_top'))

    def test_looking_at_camera_is_gaze_away(self):
        cam = sitting_torso(
            nose=(140, 150, 0.9),
            l_eye=(125, 140, 0.85),
            r_eye=(155, 140, 0.85),
            l_ear=(110, 155, 0.8),
            r_ear=(170, 155, 0.8),
        )
        self.assertTrue(is_head_up(cam, view='front_top'))
        self.assertTrue(is_gaze_away(cam, view='front_top'))

    def test_level_gaze_is_not_gaze_away(self):
        """平视还没到明显抬头。鼻与肩中线几乎齐平。"""
        level = sitting_torso(
            nose=(140, 200, 0.9),
            l_eye=(125, 190, 0.85),
            r_eye=(155, 190, 0.85),
            l_ear=(110, 185, 0.8),
            r_ear=(170, 185, 0.8),
        )
        self.assertFalse(is_head_up(level, view='front_top'))
        self.assertFalse(is_looking_aside(level, view='front_top'))
        self.assertFalse(is_gaze_away(level, view='front_top'))

    def test_turn_right_is_look_aside(self):
        aside = sitting_torso(
            nose=(190, 195, 0.9),
            l_eye=(175, 185, 0.5),
            r_eye=(200, 185, 0.85),
            l_ear=(155, 185, 0.2),
            r_ear=(210, 185, 0.85),
        )
        self.assertTrue(is_looking_aside(aside, view='front_top'))


class SideTopTest(unittest.TestCase):
    def test_profile_looking_at_screen_is_not_aside(self):
        profile = sitting_torso(
            l_shoulder=(120, 200, 0.9),
            r_shoulder=(150, 205, 0.45),
            nose=(175, 175, 0.85),
            l_eye=(160, 168, 0.8),
            l_ear=(125, 165, 0.85),
        )
        self.assertFalse(is_looking_aside(profile, view='side_top'))
        self.assertFalse(is_gaze_away(profile, view='side_top'))

    def test_turned_toward_camera_is_aside(self):
        frontal = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(125, 160, 0.85),
            r_eye=(155, 160, 0.85),
            l_ear=(110, 165, 0.7),
            r_ear=(170, 165, 0.7),
        )
        self.assertTrue(is_looking_aside(frontal, view='side_top'))
        self.assertTrue(is_gaze_away(frontal, view='side_top'))

    def test_nose_above_ear_is_head_up(self):
        """侧上方只见侧脸时，抬头不再单独算不看屏幕。"""
        raised = sitting_torso(
            l_shoulder=(120, 200, 0.9),
            r_shoulder=(150, 205, 0.45),
            nose=(175, 140, 0.85),
            l_eye=(160, 150, 0.8),
            l_ear=(125, 165, 0.85),
        )
        self.assertTrue(is_head_up(raised, view='side_top'))
        self.assertFalse(is_looking_aside(raised, view='side_top'))
        self.assertFalse(is_gaze_away(raised, view='side_top'))


class TopViewTest(unittest.TestCase):
    def test_head_toward_desk_is_not_aside(self):
        desk = sitting_torso(
            l_ear=(115, 155, 0.8),
            r_ear=(165, 155, 0.8),
            nose=(140, 150, 0.4),
        )
        self.assertFalse(is_looking_aside(desk, view='top'))
        self.assertFalse(is_gaze_away(desk, view='top'))

    def test_head_along_shoulders_is_aside(self):
        aside = sitting_torso(
            l_ear=(165, 195, 0.8),
            r_ear=(200, 200, 0.7),
            nose=(190, 200, 0.35),
        )
        self.assertTrue(is_looking_aside(aside, view='top'))


class HandsAndFallTest(unittest.TestCase):
    def test_cover_mouth(self):
        # 鼻 (140,170)，眼 (140,155)，鼻眼距 15，3 倍是 45。腕距鼻约 2.8。
        cover = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(130, 158, 0.8),
            r_eye=(150, 158, 0.8),
            r_wrist=(142, 172, 0.9),
        )
        self.assertTrue(is_cover_mouth(cover, view='front_top'))
        self.assertTrue(is_cover_mouth(cover, view='back_top'))
        self.assertTrue(is_cover_mouth(cover, view='side_top'))
        self.assertTrue(is_cover_mouth(cover, view='top'))

    def test_cover_mouth_uses_either_wrist(self):
        cover = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(140, 155, 0.85),
            l_wrist=(138, 174, 0.8),
        )
        self.assertTrue(is_cover_mouth(cover, view='front_top'))

    def test_one_eye_is_enough_for_cover_mouth(self):
        cover = sitting_torso(
            nose=(140, 170, 0.9),
            r_eye=(148, 158, 0.7),
            l_wrist=(141, 171, 0.9),
        )
        self.assertTrue(is_cover_mouth(cover, view='top'))

    def test_missing_nose_is_not_cover_mouth(self):
        no_nose = sitting_torso(
            l_eye=(130, 155, 0.9),
            r_eye=(150, 155, 0.9),
            r_wrist=(140, 170, 0.9),
        )
        self.assertFalse(is_cover_mouth(no_nose, view='front_top'))

    def test_missing_both_eyes_is_not_cover_mouth(self):
        no_eyes = sitting_torso(
            nose=(140, 170, 0.9),
            l_ear=(115, 165, 0.8),
            r_ear=(165, 165, 0.8),
            r_wrist=(142, 172, 0.9),
        )
        self.assertFalse(is_cover_mouth(no_eyes, view='back_top'))

    def test_wrist_farther_than_three_nose_eye_is_not_cover_mouth(self):
        # 鼻眼距 15，3 倍是 45。手腕在鼻子正下方 46 像素。
        far = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(140, 155, 0.9),
            r_eye=(155, 155, 0.4),
            r_wrist=(140, 216, 0.9),
        )
        self.assertFalse(is_cover_mouth(far, view='front_top'))

    def test_low_conf_wrist_is_not_cover_mouth(self):
        ghost = sitting_torso(
            nose=(140, 170, 0.9),
            l_eye=(140, 155, 0.85),
            r_wrist=(142, 172, 0.26),
        )
        self.assertFalse(is_cover_mouth(ghost, view='front_top'))
        self.assertFalse(is_cover_mouth(ghost, view='back_top'))
        self.assertFalse(is_cover_mouth(ghost, view='side_top'))

    def test_sitting_is_not_fall(self):
        sit = sitting_torso(
            l_ear=(115, 155, 0.85),
            r_ear=(165, 155, 0.85),
        )
        self.assertFalse(is_fall(sit, view='back_top'))
        self.assertFalse(is_standing(sit, view='back_top'))

    def test_lying_is_fall(self):
        lie = kps(
            l_shoulder=(100, 200, 0.9),
            r_shoulder=(180, 205, 0.9),
            l_hip=(280, 210, 0.85),
            r_hip=(350, 215, 0.85),
            l_ear=(80, 198, 0.7),
            r_ear=(90, 202, 0.7),
        )
        self.assertTrue(is_fall(lie, view='back_top'))


class _Box:
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


class FingerClickWatchTest(unittest.TestCase):
    """肩宽 80。手表在左手腕，右手靠近才算点击。"""

    def setUp(self):
        self.watch = _Box(80, 240, 100, 260)

    def _person(self, right_wrist):
        return sitting_torso(
            l_wrist=(90, 250, 0.9),
            r_wrist=(*right_wrist, 0.9),
        )

    def test_other_hand_on_watch_is_click(self):
        self.assertTrue(is_finger_click_watch(self._person((125, 250)), [self.watch]))

    def test_wearing_without_other_hand_is_not_click(self):
        self.assertFalse(is_finger_click_watch(self._person((170, 260)), [self.watch]))

    def test_missing_wrist_is_not_click(self):
        kps_one_hand = sitting_torso(l_wrist=(90, 250, 0.9))
        self.assertFalse(is_finger_click_watch(kps_one_hand, [self.watch]))

    def test_no_watch_box_is_not_click(self):
        self.assertFalse(is_finger_click_watch(self._person((125, 250)), []))


class RisingCountTest(unittest.TestCase):
    def test_one_click_triggers_immediately(self):
        state = {}
        now = datetime(2026, 10, 8, 9, 0, 0)
        self.assertTrue(accumulate_rising_count(state, True, now, 1, 30, hold_contact=True))
        self.assertFalse(accumulate_rising_count(
            state, True, now + timedelta(seconds=1), 1, 30, hold_contact=True
        ))
        self.assertFalse(accumulate_rising_count(
            state, False, now + timedelta(seconds=2), 1, 30, hold_contact=True
        ))
        self.assertTrue(accumulate_rising_count(
            state, True, now + timedelta(seconds=3), 1, 30, hold_contact=True
        ))

    def test_glasses_needs_three_separate_touches(self):
        state = {}
        now = datetime(2026, 10, 8, 9, 0, 0)
        self.assertFalse(accumulate_rising_count(state, True, now, 3, 30))
        self.assertFalse(accumulate_rising_count(state, True, now + timedelta(seconds=1), 3, 30))
        self.assertFalse(accumulate_rising_count(state, False, now + timedelta(seconds=2), 3, 30))
        self.assertFalse(accumulate_rising_count(state, True, now + timedelta(seconds=3), 3, 30))
        self.assertFalse(accumulate_rising_count(state, False, now + timedelta(seconds=4), 3, 30))
        self.assertTrue(accumulate_rising_count(state, True, now + timedelta(seconds=5), 3, 30))

    def test_window_resets_old_clicks(self):
        state = {}
        now = datetime(2026, 10, 8, 9, 0, 0)
        self.assertFalse(accumulate_rising_count(state, True, now, 2, 30, hold_contact=True))
        self.assertFalse(accumulate_rising_count(
            state, False, now + timedelta(seconds=31), 2, 30, hold_contact=True
        ))
        self.assertFalse(accumulate_rising_count(
            state, True, now + timedelta(seconds=32), 2, 30, hold_contact=True
        ))


class StandingByBoxTest(unittest.TestCase):
    def test_tall_box_is_standing(self):
        self.assertTrue(is_standing_by_box(_Box(10, 10, 50, 130), 1.6))

    def test_short_box_is_sitting(self):
        self.assertFalse(is_standing_by_box(_Box(10, 10, 110, 90), 1.6))

    def test_threshold_is_configurable(self):
        box = _Box(0, 0, 100, 150)
        self.assertFalse(is_standing_by_box(box, 1.6))
        self.assertTrue(is_standing_by_box(box, 1.5))


def _straight_legs(**extra):
    base = dict(
        l_shoulder=(100, 80, 0.9),
        r_shoulder=(180, 80, 0.9),
        l_hip=(112, 200, 0.9),
        r_hip=(168, 200, 0.9),
        l_knee=(114, 300, 0.9),
        r_knee=(166, 300, 0.9),
        l_ankle=(116, 400, 0.9),
        r_ankle=(164, 400, 0.9),
    )
    base.update(extra)
    return kps(**base)


TALL_BOX = _Box(60, 40, 230, 430)
SHORT_BOX = _Box(60, 80, 260, 200)


class DeskStandingTest(unittest.TestCase):
    def test_no_skeleton_skips_even_when_the_box_is_tall(self):
        self.assertFalse(is_desk_standing(None, TALL_BOX, 1.6))
        blank = [[0.0, 0.0, 0.0] for _ in range(17)]
        self.assertFalse(is_desk_standing(blank, TALL_BOX, 1.6))
        hit, reason = explain_scene('desk_stand', None, TALL_BOX, {'min_height_width': 1.6}, 'back_top')
        self.assertFalse(hit)
        self.assertIn('没有骨骼点', reason)

    def test_tall_box_and_one_straight_leg_is_standing(self):
        points = _straight_legs(
            l_knee=(40, 250, 0.9),
            l_ankle=(112, 320, 0.9),
        )
        self.assertTrue(is_desk_standing(points, TALL_BOX, 1.6))

    def test_both_knees_bent_is_not_standing(self):
        points = _straight_legs(
            l_knee=(40, 250, 0.9),
            l_ankle=(112, 320, 0.9),
            r_knee=(240, 250, 0.9),
            r_ankle=(168, 320, 0.9),
        )
        self.assertFalse(is_desk_standing(points, TALL_BOX, 1.6))
        _hit, reason = explain_scene('desk_stand', points, TALL_BOX, {'min_height_width': 1.6}, 'back_top')
        self.assertIn('弯曲', reason)

    def test_short_box_blocks_a_straight_leg(self):
        self.assertFalse(is_desk_standing(_straight_legs(), SHORT_BOX, 1.6))
        _hit, reason = explain_scene('desk_stand', _straight_legs(), SHORT_BOX, {'min_height_width': 1.6}, 'back_top')
        self.assertIn('不再看腿', reason)

    def test_straight_knees_with_folded_hips_are_sitting(self):
        """坐着把腿伸向前方：膝角接近伸直，肩-髋-膝弯着，不能当成站立。"""
        points = _straight_legs(
            l_knee=(70, 240, 0.9),
            r_knee=(210, 240, 0.9),
            l_ankle=(20, 288, 0.9),
            r_ankle=(260, 288, 0.9),
        )
        self.assertTrue(is_desk_standing(points, TALL_BOX, 1.6, 150, 90))
        self.assertFalse(is_desk_standing(points, TALL_BOX, 1.6))
        _hit, reason = explain_scene('desk_stand', points, TALL_BOX, {'min_height_width': 1.6}, 'back_top')
        self.assertIn('上下身', reason)
        self.assertIn('弯曲', reason)


class FingerPointTest(unittest.TestCase):
    def _reaching(self, **extra):
        pose = dict(
            r_elbow=(230, 150, 0.9),
            r_wrist=(190, 240, 0.9),
        )
        pose.update(extra)
        return _straight_legs(**pose)

    def test_forward_reach_with_bent_elbow_counts(self):
        points = self._reaching()
        self.assertTrue(is_finger_point(points, True, 'back_top', TALL_BOX))
        hit, reason = explain_scene('finger_point', points, TALL_BOX, {'require_standing': True}, 'back_top')
        self.assertTrue(hit)
        self.assertIn('前伸', reason)

    def test_wrist_above_elbow_is_not_a_reach(self):
        points = self._reaching(r_elbow=(200, 70, 0.9), r_wrist=(210, 40, 0.9))
        self.assertFalse(is_finger_point(points, True, 'back_top', TALL_BOX))

    def test_folded_elbow_is_not_a_point(self):
        points = self._reaching(r_elbow=(230, 200, 0.9), r_wrist=(150, 190, 0.9))
        self.assertFalse(is_finger_point(points, True, 'back_top', TALL_BOX))

    def test_straight_elbow_is_not_a_point(self):
        """手臂几乎伸直（约 160°）是挂在身侧，不是弯臂指屏。旧上限 180 也要收成 130。"""
        points = self._reaching(r_elbow=(200, 160, 0.9), r_wrist=(190, 250, 0.9))
        self.assertFalse(is_finger_point(points, True, 'back_top', TALL_BOX))
        hit, reason = explain_scene(
            'finger_point', points, TALL_BOX, {'elbow_max_degrees': 180}, 'back_top',
        )
        self.assertFalse(hit)
        self.assertIn('100–130', reason)

    def test_reach_without_standing_is_rejected(self):
        self.assertFalse(is_finger_point(self._reaching(), True, 'back_top', SHORT_BOX))

    def test_reach_can_skip_the_standing_check(self):
        points = kps(
            l_shoulder=(100, 80, 0.9),
            r_shoulder=(180, 80, 0.9),
            l_hip=(112, 200, 0.9),
            r_hip=(168, 200, 0.9),
            r_elbow=(230, 150, 0.9),
            r_wrist=(190, 240, 0.9),
        )
        self.assertTrue(is_finger_point(points, False, 'back_top', SHORT_BOX))

    def test_preview_rejects_a_reach_that_is_not_standing(self):
        hit, reason = explain_scene(
            'finger_point', self._reaching(), SHORT_BOX, {'require_standing': False}, 'back_top',
        )
        self.assertFalse(hit)
        self.assertIn('站立', reason)


def _turned_face(**extra):
    base = dict(
        nose=(140, 40, 0.9),
        l_eye=(125, 38, 0.85),
        r_eye=(155, 38, 0.85),
        l_ear=(110, 42, 0.7),
        r_ear=(170, 42, 0.7),
    )
    base.update(extra)
    return _straight_legs(**base)


class GazeAwayStandingGateTest(unittest.TestCase):
    def test_standing_full_face_is_not_gaze_away(self):
        points = _turned_face()
        self.assertTrue(is_desk_standing(points, TALL_BOX, 1.6))
        self.assertTrue(is_gaze_away(points, view='back_top'))
        self.assertFalse(is_gaze_away(points, view='back_top', box=TALL_BOX))
        hit, reason = explain_scene('gaze_away', points, TALL_BOX, {}, 'back_top')
        self.assertFalse(hit)
        self.assertIn('不报长时间不看屏幕', reason)

    def test_sitting_full_face_is_still_gaze_away(self):
        points = _turned_face()
        self.assertFalse(is_desk_standing(points, SHORT_BOX, 1.6))
        self.assertTrue(is_gaze_away(points, view='back_top', box=SHORT_BOX))
        hit, reason = explain_scene('gaze_away', points, SHORT_BOX, {}, 'back_top')
        self.assertTrue(hit)
        self.assertNotIn('不报长时间不看屏幕', reason)

    def test_tall_box_with_feet_under_body_is_not_gaze_away_when_knees_bend(self):
        """站着但膝盖没到 150°。高框且脚在髋下方，仍不报不看屏幕。"""
        points = _straight_legs(
            nose=(140, 40, 0.9),
            l_eye=(125, 38, 0.85),
            r_eye=(155, 38, 0.85),
            l_ear=(110, 42, 0.7),
            r_ear=(170, 42, 0.7),
            l_knee=(170, 280, 0.9),
            r_knee=(50, 280, 0.9),
            l_ankle=(118, 400, 0.9),
            r_ankle=(162, 400, 0.9),
        )
        self.assertFalse(is_desk_standing(points, TALL_BOX, 1.6))
        self.assertFalse(is_gaze_away(points, view='back_top', box=TALL_BOX))
        hit, reason = explain_scene('gaze_away', points, TALL_BOX, {}, 'back_top')
        self.assertFalse(hit)
        self.assertIn('脚在髋下方', reason)
        self.assertIn('不报长时间不看屏幕', reason)

    def test_legs_stretched_forward_on_a_tall_box_are_still_gaze_away(self):
        """坐着把腿伸向前方：脚的横向偏移更大，高框也不能当成站着。"""
        points = _straight_legs(
            nose=(140, 40, 0.9),
            l_eye=(125, 38, 0.85),
            r_eye=(155, 38, 0.85),
            l_ear=(110, 42, 0.7),
            r_ear=(170, 42, 0.7),
            l_knee=(70, 240, 0.9),
            r_knee=(210, 240, 0.9),
            l_ankle=(20, 288, 0.9),
            r_ankle=(260, 288, 0.9),
        )
        self.assertFalse(is_desk_standing(points, TALL_BOX, 1.6))
        self.assertTrue(is_gaze_away(points, view='back_top', box=TALL_BOX))
        hit, reason = explain_scene('gaze_away', points, TALL_BOX, {}, 'back_top')
        self.assertTrue(hit)
        self.assertNotIn('不报长时间不看屏幕', reason)

    def test_tall_box_without_legs_is_still_gaze_away(self):
        """只有高框、没有腿时不能当成站着，转头仍要报。"""
        points = _turned_face(
            l_hip=(0, 0, 0),
            r_hip=(0, 0, 0),
            l_knee=(0, 0, 0),
            r_knee=(0, 0, 0),
            l_ankle=(0, 0, 0),
            r_ankle=(0, 0, 0),
        )
        self.assertFalse(is_desk_standing(points, TALL_BOX, 1.6))
        self.assertTrue(is_gaze_away(points, view='back_top', box=TALL_BOX))


class ExplainSceneTest(unittest.TestCase):
    def test_missing_shoulders_says_points_are_incomplete(self):
        points = kps(nose=(140, 160, 0.9))
        hit, reason = explain_scene('head_down', points, None, {'pitch_degrees': 30}, 'front_top')
        self.assertFalse(hit)
        self.assertIn('缺', reason)
        self.assertFalse(is_head_down(points, 30, 'front_top'))

    def test_keypoint_rows_mark_low_confidence_unusable(self):
        points = kps(nose=(10, 20, 0.1), l_shoulder=(8, 40, 1), r_shoulder=(56, 40, 1))
        rows = keypoint_debug_rows(points)
        self.assertEqual(len(rows), 17)
        self.assertFalse(rows[0]['ok'])
        self.assertEqual(rows[0]['c'], 0.1)
        self.assertTrue(rows[5]['ok'])
        self.assertEqual(rows[5]['x'], 8.0)


class _GlassesBox:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    @property
    def center(self):
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


class PersonHasGlassesTest(unittest.TestCase):
    def test_overlap_counts_when_center_is_outside_the_head(self):
        points = kps(
            l_eye=(130, 100, 0.9),
            r_eye=(150, 100, 0.9),
            l_shoulder=(100, 200, 0.9),
            r_shoulder=(180, 200, 0.9),
        )
        person = _GlassesBox(40, 40, 240, 400)
        hanging = _GlassesBox(160, 110, 220, 170)
        self.assertFalse(
            102 <= hanging.center[0] <= 178 and 72 <= hanging.center[1] <= 128
        )
        self.assertTrue(person_has_glasses(person, points, [hanging]))
        self.assertFalse(person_has_glasses(person, points, [_GlassesBox(300, 300, 340, 340)]))

    def test_without_head_points_uses_the_upper_body(self):
        person = _GlassesBox(0, 0, 100, 200)
        self.assertTrue(person_has_glasses(person, None, [_GlassesBox(20, 10, 60, 50)]))
        self.assertFalse(person_has_glasses(person, None, [_GlassesBox(20, 140, 60, 180)]))


if __name__ == '__main__':
    unittest.main()
