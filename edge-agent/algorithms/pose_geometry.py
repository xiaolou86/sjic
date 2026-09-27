"""
按摄像头安装位置解释 YOLO-Pose COCO 17 关键点。

科目一考场摄像头几乎都是高位俯视，考生正常看屏幕就是低头。
用正脸相机的 yaw/pitch（鼻相对肩中线）会把正常考试判成张望/不看屏幕。
"""
import math

# COCO 17 keypoints
NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_ANKLE, R_ANKLE = 15, 16

MOUNT_POSITIONS = ('front_top', 'back_top', 'side_top', 'top')
DEFAULT_MOUNT_POSITION = 'back_top'


def normalize_mount_position(value):
    v = (value or '').strip()
    return v if v in MOUNT_POSITIONS else DEFAULT_MOUNT_POSITION


def _kp_ok(kps, idx, min_conf=0.25):
    if kps is None or idx >= len(kps):
        return False
    x, y, c = kps[idx]
    return c >= min_conf and x > 0 and y > 0


def _kp(kps, idx):
    return kps[idx][0], kps[idx][1]


def _conf(kps, idx):
    if kps is None or idx >= len(kps):
        return 0.0
    return float(kps[idx][2] or 0.0)


def _shoulder_width(kps, default=80.0):
    if _kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER):
        return max(abs(_kp(kps, R_SHOULDER)[0] - _kp(kps, L_SHOULDER)[0]), 1.0)
    return default


def _scale(kps):
    return max(_shoulder_width(kps), 40.0)


def _midpoint(kps, i, j, min_conf=0.25):
    if not (_kp_ok(kps, i, min_conf) and _kp_ok(kps, j, min_conf)):
        return None
    a, b = _kp(kps, i), _kp(kps, j)
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def head_center(kps):
    pts = []
    for i in (NOSE, L_EYE, R_EYE, L_EAR, R_EAR):
        if _kp_ok(kps, i):
            pts.append(_kp(kps, i))
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def face_visible(kps):
    """正脸可见：鼻 + 至少一只眼。后脑视角下模型瞎猜鼻子不算。"""
    if not _kp_ok(kps, NOSE, 0.4):
        return False
    return _kp_ok(kps, L_EYE, 0.35) or _kp_ok(kps, R_EYE, 0.35)


def ear_asymmetry(kps):
    """两耳置信度差，0~1。侧转头时一侧耳被挡住。"""
    cl, cr = _conf(kps, L_EAR), _conf(kps, R_EAR)
    tot = cl + cr
    if tot < 0.2:
        return 0.0
    return abs(cl - cr) / tot


def estimate_yaw_pitch(kps):
    """正脸相机粗略 yaw/pitch（度）。正 yaw=左转脸，正 pitch=画面向下。"""
    if not (_kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER) and _kp_ok(kps, NOSE)):
        return None, None
    ls, rs, nose = _kp(kps, L_SHOULDER), _kp(kps, R_SHOULDER), _kp(kps, NOSE)
    mid_x = (ls[0] + rs[0]) / 2.0
    mid_y = (ls[1] + rs[1]) / 2.0
    sw = max(abs(rs[0] - ls[0]), 1.0)
    yaw = max(-90.0, min(90.0, ((nose[0] - mid_x) / sw) * 90.0))
    pitch = max(-90.0, min(90.0, ((nose[1] - mid_y) / sw) * 90.0))
    return yaw, pitch


def _head_axis_ratios(kps):
    """
    头相对肩线的投影：along=沿双肩，perp=垂直于双肩（画面内）。
    后上方/正上方看屏：|perp| 大于 |along|；张望时 along 变大。
    """
    mid = _midpoint(kps, L_SHOULDER, R_SHOULDER)
    hc = head_center(kps)
    if mid is None or hc is None:
        return None, None
    ls, rs = _kp(kps, L_SHOULDER), _kp(kps, R_SHOULDER)
    dx, dy = rs[0] - ls[0], rs[1] - ls[1]
    length = math.hypot(dx, dy)
    if length < 8:
        return None, None
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    hx, hy = hc[0] - mid[0], hc[1] - mid[1]
    sw = _scale(kps)
    return (hx * ux + hy * uy) / sw, (hx * px + hy * py) / sw


def _neck_ratio(kps):
    mid = _midpoint(kps, L_SHOULDER, R_SHOULDER)
    hc = head_center(kps)
    if mid is None or hc is None:
        return None
    return abs(hc[1] - mid[1]) / _scale(kps)


def _head_hip_ratio(kps):
    hc = head_center(kps)
    hip = _midpoint(kps, L_HIP, R_HIP, 0.2)
    if hc is None or hip is None:
        return None
    return math.hypot(hc[0] - hip[0], hc[1] - hip[1]) / _scale(kps)


def is_looking_aside(kps, yaw_degrees=45, view=DEFAULT_MOUNT_POSITION):
    """左右张望：偷看邻座。正常低头看屏不算。"""
    view = normalize_mount_position(view)
    if kps is None:
        return False
    yaw_ref = max(float(yaw_degrees or 45), 1.0)
    scale = yaw_ref / 45.0

    if view == 'front_top':
        yaw, _ = estimate_yaw_pitch(kps)
        if yaw is not None and abs(yaw) >= yaw_ref:
            return True
        return ear_asymmetry(kps) >= 0.55 * scale and face_visible(kps)

    if view == 'back_top':
        if face_visible(kps):
            return False
        along, _ = _head_axis_ratios(kps)
        shifted = along is not None and abs(along) >= 0.28 * scale
        cl, cr = _conf(kps, L_EAR), _conf(kps, R_EAR)
        turned = (cl + cr) >= 0.5 and ear_asymmetry(kps) >= 0.40 * scale
        if shifted and turned:
            return True
        return shifted and along is not None and abs(along) >= 0.42 * scale

    if view == 'side_top':
        both_eyes = _kp_ok(kps, L_EYE, 0.35) and _kp_ok(kps, R_EYE, 0.35)
        if both_eyes:
            return True
        no_face = not _kp_ok(kps, NOSE, 0.3) and not _kp_ok(kps, L_EYE, 0.3) and not _kp_ok(kps, R_EYE, 0.3)
        return no_face and (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR))

    along, perp = _head_axis_ratios(kps)
    if along is None or perp is None:
        return False
    return abs(along) >= 0.28 * scale and abs(along) >= abs(perp) * 0.85


def is_head_down(kps, pitch_degrees=30, view=DEFAULT_MOUNT_POSITION):
    """
    过度埋头（看腿上/桌下），不是正常看屏幕。
    前上方高位下，看屏幕本身就会让鼻子低于肩膀，必须抬高阈值。
    """
    view = normalize_mount_position(view)
    if kps is None:
        return False
    pitch_ref = float(pitch_degrees or 30)

    if view == 'front_top':
        _, pitch = estimate_yaw_pitch(kps)
        if pitch is None:
            return False
        return pitch >= pitch_ref + 28.0

    if view == 'side_top':
        if not (_kp_ok(kps, NOSE) and (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR))):
            return False
        nose_y = _kp(kps, NOSE)[1]
        ear_ys = [_kp(kps, i)[1] for i in (L_EAR, R_EAR) if _kp_ok(kps, i)]
        if not ear_ys:
            return False
        drop = (nose_y - (sum(ear_ys) / len(ear_ys))) / _scale(kps)
        return drop >= 0.22 + pitch_ref / 200.0

    neck = _neck_ratio(kps)
    if neck is not None and neck < 0.16:
        return True
    hh = _head_hip_ratio(kps)
    return hh is not None and hh < 0.55


def is_gaze_away(kps, yaw_degrees=25, pitch_degrees=25, view=DEFAULT_MOUNT_POSITION):
    """不看屏幕：张望、回头、抬头看人，或过度埋头。正常看题不算。"""
    view = normalize_mount_position(view)
    if kps is None:
        return False
    if is_looking_aside(kps, yaw_degrees, view):
        return True
    if is_head_down(kps, pitch_degrees, view):
        return True

    if view == 'front_top':
        _, pitch = estimate_yaw_pitch(kps)
        return pitch is not None and pitch < 8.0

    if view == 'back_top':
        return face_visible(kps)

    if view == 'side_top':
        if not _kp_ok(kps, NOSE):
            return False
        ear_ys = [_kp(kps, i)[1] for i in (L_EAR, R_EAR) if _kp_ok(kps, i)]
        if not ear_ys:
            return False
        # 抬头：鼻高于耳
        return _kp(kps, NOSE)[1] < (sum(ear_ys) / len(ear_ys)) - 0.12 * _scale(kps)

    return False


def is_chin_rest(kps, view=DEFAULT_MOUNT_POSITION):
    """手腕靠近下颌/头下部。后上方看不到下巴时，用头中心代替鼻尖。"""
    view = normalize_mount_position(view)
    anchor = None
    if view in ('back_top', 'top'):
        anchor = head_center(kps)
    if anchor is None and _kp_ok(kps, NOSE):
        anchor = _kp(kps, NOSE)
    if anchor is None:
        return False
    sw = _scale(kps)
    for wi in (L_WRIST, R_WRIST):
        if not _kp_ok(kps, wi):
            continue
        wx, wy = _kp(kps, wi)
        dist = math.hypot(wx - anchor[0], wy - anchor[1]) / sw
        if dist < 0.58 and wy >= anchor[1] - 0.2 * sw:
            return True
    return False


def is_cover_mouth(kps, view=DEFAULT_MOUNT_POSITION):
    """捂嘴：手腕贴近口鼻；后上方改为手腕压在头附近。"""
    view = normalize_mount_position(view)
    anchor = head_center(kps) if view in ('back_top', 'top') else None
    if anchor is None and _kp_ok(kps, NOSE):
        anchor = _kp(kps, NOSE)
    if anchor is None:
        return False
    sw = _scale(kps)
    for wi in (L_WRIST, R_WRIST):
        if not _kp_ok(kps, wi):
            continue
        wx, wy = _kp(kps, wi)
        dist = math.hypot(wx - anchor[0], wy - anchor[1]) / sw
        if view in ('back_top', 'top'):
            if dist < 0.40:
                return True
        elif dist < 0.42 and abs(wy - anchor[1]) < 0.35 * sw and wy >= anchor[1] - 0.15 * sw:
            return True
    return False


def is_wrist_near_ear(kps, dist_ratio=0.28):
    sw = _scale(kps)
    ears = [_kp(kps, ei) for ei in (L_EAR, R_EAR) if _kp_ok(kps, ei)]
    if not ears:
        return False
    for wi in (L_WRIST, R_WRIST):
        if not _kp_ok(kps, wi):
            continue
        wx, wy = _kp(kps, wi)
        for ex, ey in ears:
            if math.hypot(wx - ex, wy - ey) / sw < float(dist_ratio):
                return True
    return False


def _head_rect(kps):
    """耳、眼、鼻围成的头部区域，向外扩一点肩宽。点不够时返回 None。"""
    idxs = (NOSE, L_EYE, R_EYE, L_EAR, R_EAR)
    pts = [_kp(kps, idx) for idx in idxs if _kp_ok(kps, idx)]
    if len(pts) < 2:
        return None
    pad = 0.35 * _scale(kps)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _point_in_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def _point_in_upper_body(box, x, y):
    if box is None:
        return False
    x1, y1, x2, y2 = float(box.x1), float(box.y1), float(box.x2), float(box.y2)
    if x2 <= x1 or y2 <= y1:
        return False
    return x1 <= x <= x2 and y1 <= y <= y1 + 0.5 * (y2 - y1)


def person_has_glasses(box, kps, glasses_boxes):
    """眼镜框中心落在头部区域（关键点不足时用人体框上半部分）才算戴着眼镜。"""
    if not glasses_boxes:
        return False
    head = _head_rect(kps) if kps is not None else None
    for glasses in glasses_boxes:
        cx, cy = glasses.center
        if head is not None:
            if _point_in_rect(cx, cy, head):
                return True
            continue
        if _point_in_upper_body(box, cx, cy):
            return True
    return False


def is_standing(kps, box=None, view=DEFAULT_MOUNT_POSITION):
    view = normalize_mount_position(view)
    if kps is not None:
        if _kp_ok(kps, L_HIP) and _kp_ok(kps, L_ANKLE):
            if _kp(kps, L_ANKLE)[1] > _kp(kps, L_HIP)[1] + 25:
                return True
        if _kp_ok(kps, R_HIP) and _kp_ok(kps, R_ANKLE):
            if _kp(kps, R_ANKLE)[1] > _kp(kps, R_HIP)[1] + 25:
                return True
    if view == 'top':
        return False
    if box is not None:
        w = max(float(box.x2 - box.x1), 1.0)
        h = max(float(box.y2 - box.y1), 1.0)
        if h / w >= 1.45:
            return True
    return False


def _head_above_torso(kps, min_ratio=0.16):
    if kps is None:
        return False
    head_ys = [_kp(kps, i)[1] for i in (NOSE, L_EYE, R_EYE, L_EAR, R_EAR) if _kp_ok(kps, i, 0.3)]
    if not head_ys:
        return False
    head_y = min(head_ys)
    torso_ys = []
    sh = _midpoint(kps, L_SHOULDER, R_SHOULDER, 0.3)
    hip = _midpoint(kps, L_HIP, R_HIP, 0.3)
    if sh:
        torso_ys.append(sh[1])
    if hip:
        torso_ys.append(hip[1])
    if not torso_ys:
        return False
    return head_y < min(torso_ys) - min_ratio * _scale(kps)


def _torso_nearly_horizontal(kps, max_degrees=16):
    if not (
        _kp_ok(kps, L_SHOULDER, 0.3) and _kp_ok(kps, R_SHOULDER, 0.3)
        and _kp_ok(kps, L_HIP, 0.3) and _kp_ok(kps, R_HIP, 0.3)
    ):
        return False
    sy = (_kp(kps, L_SHOULDER)[1] + _kp(kps, R_SHOULDER)[1]) / 2.0
    hy = (_kp(kps, L_HIP)[1] + _kp(kps, R_HIP)[1]) / 2.0
    sx = (_kp(kps, L_SHOULDER)[0] + _kp(kps, R_SHOULDER)[0]) / 2.0
    hx = (_kp(kps, L_HIP)[0] + _kp(kps, R_HIP)[0]) / 2.0
    dx, dy = abs(hx - sx), abs(hy - sy)
    length = math.hypot(dx, dy)
    if length < 10:
        return False
    return math.degrees(math.atan2(dy, dx)) <= float(max_degrees)


def is_fall(kps, box=None, peer_boxes=None, view=DEFAULT_MOUNT_POSITION):
    """倒地必须是躺姿；俯视考场坐姿/伏案不算。正上方更保守。"""
    _ = view
    if kps is None:
        return False
    if _head_above_torso(kps):
        return False
    if not _torso_nearly_horizontal(kps):
        return False
    if box is not None and peer_boxes and len(peer_boxes) >= 3:
        others = [b for b in peer_boxes if b is not None and b is not box]
        if others:
            other_cy = sorted((b.y1 + b.y2) / 2.0 for b in others)
            med_cy = other_cy[len(other_cy) // 2]
            med_h = sorted(max(b.y2 - b.y1, 1.0) for b in others)[len(others) // 2]
            my_cy = (box.y1 + box.y2) / 2.0
            if my_cy < med_cy + 0.28 * med_h:
                return False
    return True


def is_finger_point(kps, require_standing=True, view=DEFAULT_MOUNT_POSITION):
    standing = True
    if require_standing:
        standing = is_standing(kps, None, view)
        if _kp_ok(kps, L_HIP) and _kp_ok(kps, L_ANKLE):
            standing = _kp(kps, L_ANKLE)[1] > _kp(kps, L_HIP)[1] + 20
    if require_standing and not standing:
        return False
    for elbow, wrist in ((L_ELBOW, L_WRIST), (R_ELBOW, R_WRIST)):
        if _kp_ok(kps, elbow) and _kp_ok(kps, wrist):
            if _kp(kps, wrist)[1] < _kp(kps, elbow)[1] - 15:
                return True
    return False
