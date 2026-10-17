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
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

MOUNT_POSITIONS = ('front_top', 'back_top', 'side_top', 'top')
DEFAULT_MOUNT_POSITION = 'back_top'

# 髋-膝-踝夹角接近 180° 才算这条腿伸直。坐着多半弯到 120° 以下。
DESK_KNEE_STRAIGHT_DEGREES = 150.0
# 肩-髋-膝夹角接近 180° 才算上半身与下半身伸直。
# 坐着把腿伸向前方时膝角仍可能很大，但髋处多半弯到 120° 以下。140° 给站立前倾留一点余量。
DESK_HIP_STRAIGHT_DEGREES = 140.0
# 腕相对肩中点，沿躯干前下方的投影 / 肩宽。
FINGER_REACH_RATIO = 0.45
# 伸臂点屏幕时肘要张开。折回肩旁的小角度不算。
FINGER_ELBOW_MIN_DEGREES = 100.0
FINGER_ELBOW_MAX_DEGREES = 180.0


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
    sw = math.hypot(rs[0] - ls[0], rs[1] - ls[1])
    # 肩线几乎叠在一起时，用水平间距会把角度放大到 ±90。
    if sw < 8.0:
        return None, None
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


def is_head_up(kps, view=DEFAULT_MOUNT_POSITION):
    """明显抬头。俯视下正常看屏幕（头在肩前、鼻在肩下）不算。"""
    view = normalize_mount_position(view)
    if kps is None:
        return False

    if view == 'front_top':
        _, pitch = estimate_yaw_pitch(kps)
        return pitch is not None and pitch <= -15.0

    if view == 'side_top':
        if not (_kp_ok(kps, NOSE) and (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR))):
            return False
        nose_y = _kp(kps, NOSE)[1]
        ear_ys = [_kp(kps, i)[1] for i in (L_EAR, R_EAR) if _kp_ok(kps, i)]
        if not ear_ys:
            return False
        return nose_y < (sum(ear_ys) / len(ear_ys)) - 0.18 * _scale(kps)

    if not face_visible(kps):
        return False
    if not (_kp_ok(kps, NOSE) and _kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER)):
        return False
    nose_y = _kp(kps, NOSE)[1]
    shoulder_y = (_kp(kps, L_SHOULDER)[1] + _kp(kps, R_SHOULDER)[1]) / 2.0
    return (shoulder_y - nose_y) >= 0.22 * _scale(kps)


def is_gaze_away(kps, yaw_degrees=25, pitch_degrees=25, view=DEFAULT_MOUNT_POSITION):
    """不看屏幕：明显抬头，或左右观望。俯视看屏幕的低头不算。pitch_degrees 只保留兼容。"""
    _ = pitch_degrees
    view = normalize_mount_position(view)
    if kps is None:
        return False
    if is_looking_aside(kps, yaw_degrees, view):
        return True
    return is_head_up(kps, view)


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


def _point_near_box(x, y, box, margin):
    """点落在检测框内，或离框边不超过 margin。"""
    try:
        x1, y1 = float(box.x1), float(box.y1)
        x2, y2 = float(box.x2), float(box.y2)
        pad = float(margin)
    except (TypeError, ValueError, AttributeError):
        return False
    return (x1 - pad) <= x <= (x2 + pad) and (y1 - pad) <= y <= (y2 + pad)


def is_finger_click_watch(kps, watch_boxes, dist_ratio=0.50):
    """
    另一只手点击手表。

    姿态模型没有指尖，用另一侧手腕近似手指。手表框贴着一只手腕时视为佩戴；
    另一只手腕再进入这块表附近，才算一次点击。只戴表、另一只手远离时返回 False。
    距离按肩宽缩放，俯视和侧视都能用。
    """
    if kps is None or not watch_boxes:
        return False
    if not (_kp_ok(kps, L_WRIST) and _kp_ok(kps, R_WRIST)):
        return False
    margin = float(dist_ratio) * _scale(kps)
    left = _kp(kps, L_WRIST)
    right = _kp(kps, R_WRIST)
    for watch in watch_boxes:
        if _point_near_box(left[0], left[1], watch, margin) and _point_near_box(right[0], right[1], watch, margin):
            return True
    return False


def accumulate_rising_count(state, active, now, min_count, window_seconds, hold_contact=False):
    """
    active 从无到有计一次。窗口超时后重新计数。
    达到 min_count 时清空计数并返回 True。就地修改 state。
    hold_contact 为真时，同一次按住不重复计数，松开后再按才算下一次。
    """
    active = bool(active)
    try:
        min_count = int(min_count)
    except (TypeError, ValueError):
        min_count = 1
    if min_count < 1:
        min_count = 1
    try:
        window_seconds = float(window_seconds)
    except (TypeError, ValueError):
        window_seconds = 30.0

    if active and not state.get('near'):
        state['touches'] = int(state.get('touches') or 0) + 1
        state['window_start'] = state.get('window_start') or now
    state['near'] = active

    window_start = state.get('window_start')
    if window_start and (now - window_start).total_seconds() > window_seconds:
        state['touches'] = 1 if active else 0
        state['window_start'] = now if active else None

    if int(state.get('touches') or 0) >= min_count:
        state['touches'] = 0
        state['window_start'] = None
        if not hold_contact:
            state['near'] = False
        return True
    return False


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


def box_height_width_ratio(box):
    """人框高/宽。站着的人框更瘦高，坐着的考生更矮。"""
    if box is None:
        return None
    try:
        width = float(box.x2) - float(box.x1)
        height = float(box.y2) - float(box.y1)
    except (TypeError, ValueError, AttributeError):
        return None
    if width <= 1.0 or height <= 1.0:
        return None
    return height / width


def is_standing_by_box(box, min_ratio=1.6):
    """人框高/宽是否达到阈值。这只是考台边站立的前提，本身不算站着。"""
    ratio = box_height_width_ratio(box)
    if ratio is None:
        return False
    try:
        gate = float(min_ratio)
    except (TypeError, ValueError):
        gate = 1.6
    if gate <= 0:
        gate = 1.6
    return ratio >= gate


def _bounded_float(value, default, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if number < low or number > high:
        return float(default)
    return number


def _knee_gate(min_knee_degrees):
    return _bounded_float(min_knee_degrees, DESK_KNEE_STRAIGHT_DEGREES, 1.0, 179.0)


def _hip_gate(min_hip_degrees):
    return _bounded_float(min_hip_degrees, DESK_HIP_STRAIGHT_DEGREES, 1.0, 179.0)


def _finger_gates(min_reach_ratio, elbow_min_degrees, elbow_max_degrees):
    reach = _bounded_float(min_reach_ratio, FINGER_REACH_RATIO, 0.05, 5.0)
    elbow_min = _bounded_float(elbow_min_degrees, FINGER_ELBOW_MIN_DEGREES, 0.0, 180.0)
    elbow_max = _bounded_float(elbow_max_degrees, FINGER_ELBOW_MAX_DEGREES, 0.0, 180.0)
    if elbow_max < elbow_min:
        return FINGER_REACH_RATIO, FINGER_ELBOW_MIN_DEGREES, FINGER_ELBOW_MAX_DEGREES
    return reach, elbow_min, elbow_max


def _has_skeleton(kps):
    """至少一个关键点达到几何判断用的置信度。全空、字符串都当没有骨骼。"""
    if kps is None or isinstance(kps, (str, bytes)):
        return False
    try:
        count = len(kps)
    except TypeError:
        return False
    for index in range(min(count, 17)):
        if _kp_ok(kps, index):
            return True
    return False


def _joint_angle(a, b, c, min_len=8.0):
    """点 b 处的夹角，0~180°。任一段过短则返回 None。"""
    v1x, v1y = a[0] - b[0], a[1] - b[1]
    v2x, v2y = c[0] - b[0], c[1] - b[1]
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 < min_len or n2 < min_len:
        return None
    cos = (v1x * v2x + v1y * v2y) / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def _chain_angle(kps, start, joint, end):
    if not (_kp_ok(kps, start) and _kp_ok(kps, joint) and _kp_ok(kps, end)):
        return None
    return _joint_angle(_kp(kps, start), _kp(kps, joint), _kp(kps, end))


def _leg_angles(kps):
    return (
        ('左', _chain_angle(kps, L_HIP, L_KNEE, L_ANKLE), (L_HIP, L_KNEE, L_ANKLE)),
        ('右', _chain_angle(kps, R_HIP, R_KNEE, R_ANKLE), (R_HIP, R_KNEE, R_ANKLE)),
    )


def _hip_angles(kps):
    """上半身（肩-髋）与下半身（髋-膝）在髋处的夹角。180° 为挺直。"""
    return (
        ('左', _chain_angle(kps, L_SHOULDER, L_HIP, L_KNEE), (L_SHOULDER, L_HIP, L_KNEE)),
        ('右', _chain_angle(kps, R_SHOULDER, R_HIP, R_KNEE), (R_SHOULDER, R_HIP, R_KNEE)),
    )


def is_desk_standing(
    kps, box, min_ratio=1.6,
    min_knee_degrees=DESK_KNEE_STRAIGHT_DEGREES,
    min_hip_degrees=DESK_HIP_STRAIGHT_DEGREES,
):
    """
    考台边站立。
    没有骨骼点则跳过。人框高宽比只是前提。达标后至少一条腿要同时满足：
    大腿与小腿伸直，且上半身与下半身在髋处的夹角也伸直。
    坐着把腿伸向前方时膝角可以很大，髋处弯曲则滤掉。
    """
    if not _has_skeleton(kps):
        return False
    if not is_standing_by_box(box, min_ratio):
        return False
    knee_gate = _knee_gate(min_knee_degrees)
    hip_gate = _hip_gate(min_hip_degrees)
    for (_name, knee_angle, _knee_indexes), (_hip_name, hip_angle, _hip_indexes) in zip(
        _leg_angles(kps), _hip_angles(kps),
    ):
        if (
            knee_angle is not None and knee_angle >= knee_gate
            and hip_angle is not None and hip_angle >= hip_gate
        ):
            return True
    return False


def _forward_down_axis(kps):
    """
    躯干轴：肩中点指向髋中点。
    高位俯视里这条轴朝画面下方，对应人朝屏幕的前下方。
    髋画在肩上方时翻过来，使正方向朝画面下方。
    返回 (肩中点, 单位向量)；肩或髋不够、轴太短时返回 None。
    """
    shoulder = _midpoint(kps, L_SHOULDER, R_SHOULDER)
    hip = _midpoint(kps, L_HIP, R_HIP)
    if shoulder is None or hip is None:
        return None
    dx = hip[0] - shoulder[0]
    dy = hip[1] - shoulder[1]
    if dy < 0:
        dx = -dx
        dy = -dy
    length = math.hypot(dx, dy)
    if length < 8:
        return None
    return shoulder, (dx / length, dy / length)


def _wrist_reach_ratio(kps, wrist_index, axis):
    """腕相对肩中点在前下方上的投影，再除以肩宽。"""
    if axis is None or not _kp_ok(kps, wrist_index):
        return None
    origin, (ux, uy) = axis
    wx, wy = _kp(kps, wrist_index)
    return ((wx - origin[0]) * ux + (wy - origin[1]) * uy) / _scale(kps)


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


def is_finger_point(
    kps, require_standing=True, view=DEFAULT_MOUNT_POSITION, box=None,
    min_height_width=1.6, min_knee_degrees=DESK_KNEE_STRAIGHT_DEGREES,
    min_hip_degrees=DESK_HIP_STRAIGHT_DEGREES,
    min_reach_ratio=FINGER_REACH_RATIO,
    elbow_min_degrees=FINGER_ELBOW_MIN_DEGREES,
    elbow_max_degrees=FINGER_ELBOW_MAX_DEGREES,
):
    """
    伸臂点屏幕。
    需要站立时，用考台边站立的同一套结果（骨骼、人框高宽比、膝角和上下身夹角）。
    再看腕沿躯干前下方的前伸量，以及肘角是否在张开范围里。任一条手臂满足即可。
    """
    _ = view
    if not _has_skeleton(kps):
        return False
    if require_standing and not is_desk_standing(
        kps, box, min_height_width, min_knee_degrees, min_hip_degrees,
    ):
        return False
    axis = _forward_down_axis(kps)
    if axis is None:
        return False
    reach_gate, elbow_min, elbow_max = _finger_gates(
        min_reach_ratio, elbow_min_degrees, elbow_max_degrees,
    )
    for shoulder, elbow, wrist in (
        (L_SHOULDER, L_ELBOW, L_WRIST),
        (R_SHOULDER, R_ELBOW, R_WRIST),
    ):
        reach = _wrist_reach_ratio(kps, wrist, axis)
        angle = _chain_angle(kps, shoulder, elbow, wrist)
        if reach is None or angle is None:
            continue
        if reach >= reach_gate and elbow_min <= angle <= elbow_max:
            return True
    return False


KP_DEBUG_NAMES = (
    '鼻', '左眼', '右眼', '左耳', '右耳',
    '左肩', '右肩', '左肘', '右肘', '左腕', '右腕',
    '左髋', '右髋', '左膝', '右膝', '左踝', '右踝',
)


def keypoint_debug_rows(kps, min_conf=0.25):
    """17 点的坐标和是否达到几何判断用的置信度。不改判定。"""
    rows = []
    for index, name in enumerate(KP_DEBUG_NAMES):
        item = {'i': index, 'name': name, 'ok': False}
        if kps is None or index >= len(kps):
            rows.append(item)
            continue
        try:
            x = float(kps[index][0])
            y = float(kps[index][1])
            conf = float(kps[index][2]) if len(kps[index]) > 2 else 1.0
        except (TypeError, ValueError, IndexError):
            rows.append(item)
            continue
        item['x'] = round(x, 1)
        item['y'] = round(y, 1)
        item['c'] = round(conf, 2)
        item['ok'] = bool(conf >= min_conf and x > 0 and y > 0)
        rows.append(item)
    return rows


def _missing_names(kps, indexes, min_conf=0.25):
    names = []
    for index in indexes:
        if not _kp_ok(kps, index, min_conf):
            names.append(KP_DEBUG_NAMES[index])
    return names


def explain_scene(btype, kps, box, spec, view):
    """本帧几何结论。hit 与正式判断同一函数，reason 说明缺点和数值。"""
    spec = spec or {}
    view = normalize_mount_position(view)
    if btype == 'look_aside':
        return _explain_look_aside(kps, spec.get('yaw_degrees', 45), view)
    if btype == 'head_down':
        return _explain_head_down(kps, spec.get('pitch_degrees', 30), view)
    if btype == 'gaze_away':
        return _explain_gaze_away(kps, spec.get('yaw_degrees', 25), view)
    if btype == 'cover_mouth':
        return _explain_cover_mouth(kps, view)
    if btype == 'finger_point':
        return _explain_finger_point(kps, box, spec, view)
    if btype == 'desk_stand':
        return _explain_desk_stand(kps, box, spec)
    if btype == 'smart_glasses':
        return _explain_glasses_pose(kps, spec)
    if btype == 'smart_watch':
        return _explain_watch_pose(kps, spec)
    return False, '预览没有这条场景的几何说明'


def _explain_look_aside(kps, yaw_degrees, view):
    hit = is_looking_aside(kps, yaw_degrees, view)
    if kps is None:
        return hit, '没有关键点'
    yaw_ref = max(float(yaw_degrees or 45), 1.0)
    scale = yaw_ref / 45.0
    if view == 'front_top':
        yaw, _pitch = estimate_yaw_pitch(kps)
        if yaw is None:
            missing = _missing_names(kps, (NOSE, L_SHOULDER, R_SHOULDER))
            return hit, '转头角算不出来，缺 ' + '、'.join(missing or ['鼻或双肩'])
        face = face_visible(kps)
        return hit, (
            f"转头角 {yaw:.1f}°，阈值 {yaw_ref:.0f}°；"
            f"耳不对称 {ear_asymmetry(kps):.2f}（要 ≥ {0.55 * scale:.2f}）；"
            f"正脸{'可见' if face else '不可见'}"
        )
    if view == 'back_top':
        if face_visible(kps):
            return hit, '鼻和至少一只眼清楚，后上方把这当成面向屏幕，不算张望'
        along, _perp = _head_axis_ratios(kps)
        if along is None:
            missing = _missing_names(kps, (L_SHOULDER, R_SHOULDER, NOSE, L_EYE, R_EYE, L_EAR, R_EAR))
            return hit, '沿肩偏移算不出来，缺 ' + '、'.join(missing[:4] or ['双肩或头部点'])
        asym = ear_asymmetry(kps)
        return hit, (
            f"沿肩偏移 {along:.2f}（{0.28 * scale:.2f} 起算，{0.42 * scale:.2f} 单独即可）；"
            f"耳不对称 {asym:.2f}，左耳 {_conf(kps, L_EAR):.2f} 右耳 {_conf(kps, R_EAR):.2f}"
        )
    if view == 'side_top':
        both = _kp_ok(kps, L_EYE, 0.35) and _kp_ok(kps, R_EYE, 0.35)
        if both:
            return hit, '两只眼都清楚，侧上方视为转到正面'
        missing = _missing_names(kps, (NOSE, L_EYE, R_EYE, L_EAR, R_EAR), 0.3)
        return hit, '侧脸条件未同时满足。相关点：' + ('、'.join(missing) if missing else '耳或脸点置信度不够')
    along, perp = _head_axis_ratios(kps)
    if along is None or perp is None:
        return hit, '正上方需要双肩和头部点，沿肩/垂直偏移算不出来'
    return hit, (
        f"沿肩 {along:.2f}，垂直 {perp:.2f}；"
        f"要 |沿肩| ≥ {0.28 * scale:.2f} 且不小于垂直方向的 0.85 倍"
    )


def _explain_head_down(kps, pitch_degrees, view):
    hit = is_head_down(kps, pitch_degrees, view)
    if kps is None:
        return hit, '没有关键点'
    pitch_ref = float(pitch_degrees or 30)
    if view == 'front_top':
        _yaw, pitch = estimate_yaw_pitch(kps)
        if pitch is None:
            missing = _missing_names(kps, (NOSE, L_SHOULDER, R_SHOULDER))
            return hit, '低头角算不出来，缺 ' + '、'.join(missing or ['鼻或双肩'])
        return hit, f"低头角 {pitch:.1f}°，阈值 {pitch_ref + 28:.0f}°"
    if view == 'side_top':
        if not (_kp_ok(kps, NOSE) and (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR))):
            missing = _missing_names(kps, (NOSE, L_EAR, R_EAR))
            return hit, '缺 ' + '、'.join(missing or ['鼻或耳'])
        nose_y = _kp(kps, NOSE)[1]
        ear_ys = [_kp(kps, i)[1] for i in (L_EAR, R_EAR) if _kp_ok(kps, i)]
        drop = (nose_y - (sum(ear_ys) / len(ear_ys))) / _scale(kps)
        gate = 0.22 + pitch_ref / 200.0
        return hit, f"鼻相对耳下移 {drop:.2f}，阈值 {gate:.2f}"
    neck = _neck_ratio(kps)
    head_hip = _head_hip_ratio(kps)
    parts = []
    if neck is None:
        parts.append('颈长比算不出来（缺头或双肩）')
    else:
        parts.append(f"颈长比 {neck:.2f}（< 0.16 算埋头）")
    if head_hip is None:
        parts.append('头髋比算不出来（缺头或双髋）')
    else:
        parts.append(f"头髋比 {head_hip:.2f}（< 0.55 算埋头）")
    return hit, '；'.join(parts)


def _explain_head_up(kps, view):
    hit = is_head_up(kps, view)
    if kps is None:
        return hit, '没有关键点'
    if view == 'front_top':
        _yaw, pitch = estimate_yaw_pitch(kps)
        if pitch is None:
            return hit, '抬头角算不出来，缺鼻或双肩'
        return hit, f"俯仰 {pitch:.1f}°，≤ -15° 算抬头"
    if view == 'side_top':
        if not (_kp_ok(kps, NOSE) and (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR))):
            return hit, '缺鼻或耳，侧上方无法比高低'
        return hit, '鼻相对耳的高度没有达到抬头'
    if not face_visible(kps):
        return hit, '正脸不可见（要鼻置信度 ≥ 0.4 且至少一只眼 ≥ 0.35），俯视下不算抬头'
    if not (_kp_ok(kps, NOSE) and _kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER)):
        return hit, '缺鼻或双肩'
    nose_y = _kp(kps, NOSE)[1]
    shoulder_y = (_kp(kps, L_SHOULDER)[1] + _kp(kps, R_SHOULDER)[1]) / 2.0
    gap = (shoulder_y - nose_y) / _scale(kps)
    return hit, f"鼻高于肩 {gap:.2f} 个肩宽，阈值 0.22"


def _explain_gaze_away(kps, yaw_degrees, view):
    hit = is_gaze_away(kps, yaw_degrees, view=view)
    _aside_hit, aside = _explain_look_aside(kps, yaw_degrees, view)
    _up_hit, up = _explain_head_up(kps, view)
    return hit, f"张望或抬头才算。张望：{aside}。抬头：{up}"


def _explain_cover_mouth(kps, view):
    hit = is_cover_mouth(kps, view)
    if kps is None:
        return hit, '没有关键点'
    anchor = head_center(kps) if view in ('back_top', 'top') else None
    anchor_name = '头部'
    if anchor is None and _kp_ok(kps, NOSE):
        anchor = _kp(kps, NOSE)
        anchor_name = '鼻'
    if anchor is None:
        missing = _missing_names(kps, (NOSE, L_EYE, R_EYE, L_EAR, R_EAR))
        return hit, '没有可用的头或鼻子，缺 ' + '、'.join(missing or ['头部点'])
    sw = _scale(kps)
    gate = 0.40 if view in ('back_top', 'top') else 0.42
    parts = []
    for index, name in ((L_WRIST, '左腕'), (R_WRIST, '右腕')):
        if not _kp_ok(kps, index):
            parts.append(f"{name}不可用")
            continue
        wx, wy = _kp(kps, index)
        dist = math.hypot(wx - anchor[0], wy - anchor[1]) / sw
        parts.append(f"{name}距{anchor_name} {dist:.2f}")
    return hit, f"阈值 {gate:.2f} 个肩宽。" + '，'.join(parts)


def _format_joint(kps, label, angle, indexes, gate):
    if angle is None:
        missing = _missing_names(kps, indexes)
        if missing:
            return f"{label}缺{'、'.join(missing)}"
        return f"{label}线段过短"
    state = '伸直' if angle >= gate else '弯曲'
    return f"{label} {angle:.0f}°（{state}，要 ≥ {gate:.0f}°）"


def _format_leg(kps, label, knee_angle, knee_indexes, knee_gate, hip_angle, hip_indexes, hip_gate):
    knee = _format_joint(kps, f"{label}膝", knee_angle, knee_indexes, knee_gate)
    hip = _format_joint(kps, f"{label}上下身", hip_angle, hip_indexes, hip_gate)
    return f"{knee}，{hip}"


def _explain_finger_point(kps, box, spec, view):
    spec = spec or {}
    require_standing = bool(spec.get('require_standing', True))
    min_height_width = spec.get('min_height_width', 1.6)
    min_knee = spec.get('min_knee_degrees', DESK_KNEE_STRAIGHT_DEGREES)
    min_hip = spec.get('min_hip_degrees', DESK_HIP_STRAIGHT_DEGREES)
    reach_gate, elbow_min, elbow_max = _finger_gates(
        spec.get('min_reach_ratio', FINGER_REACH_RATIO),
        spec.get('elbow_min_degrees', FINGER_ELBOW_MIN_DEGREES),
        spec.get('elbow_max_degrees', FINGER_ELBOW_MAX_DEGREES),
    )
    hit = is_finger_point(
        kps, require_standing, view, box, min_height_width, min_knee, min_hip,
        reach_gate, elbow_min, elbow_max,
    )
    if not _has_skeleton(kps):
        return hit, '没有骨骼点，跳过'
    parts = []
    if require_standing:
        _stand_hit, stand_reason = _explain_desk_stand(kps, box, {
            'min_height_width': min_height_width,
            'min_knee_degrees': min_knee,
            'min_hip_degrees': min_hip,
        })
        parts.append('站立（与考台边同一套）：' + stand_reason)
    axis = _forward_down_axis(kps)
    if axis is None:
        parts.append('肩中点或髋中点不可用，前伸算不出来')
        return hit, '；'.join(parts)
    for shoulder, elbow, wrist, name in (
        (L_SHOULDER, L_ELBOW, L_WRIST, '左'),
        (R_SHOULDER, R_ELBOW, R_WRIST, '右'),
    ):
        reach = _wrist_reach_ratio(kps, wrist, axis)
        angle = _chain_angle(kps, shoulder, elbow, wrist)
        if reach is None or angle is None:
            missing = _missing_names(kps, (shoulder, elbow, wrist))
            parts.append(f"{name}臂缺{'、'.join(missing or ['肩、肘或腕'])}")
            continue
        parts.append(
            f"{name}前伸 {reach:.2f}（≥ {reach_gate:.2f}），"
            f"肘角 {angle:.0f}°（{elbow_min:.0f}–{elbow_max:.0f}°）"
        )
    return hit, '；'.join(parts)


def _ratio_gate(min_ratio):
    try:
        gate = float(min_ratio)
    except (TypeError, ValueError):
        gate = 1.6
    if gate <= 0:
        gate = 1.6
    return gate


def _explain_desk_stand(kps, box, spec):
    spec = spec or {}
    ratio_gate = _ratio_gate(spec.get('min_height_width', 1.6))
    knee_gate = _knee_gate(spec.get('min_knee_degrees', DESK_KNEE_STRAIGHT_DEGREES))
    hip_gate = _hip_gate(spec.get('min_hip_degrees', DESK_HIP_STRAIGHT_DEGREES))
    hit = is_desk_standing(kps, box, ratio_gate, knee_gate, hip_gate)
    if not _has_skeleton(kps):
        return hit, '没有骨骼点，跳过站立判断'
    ratio = box_height_width_ratio(box)
    if ratio is None:
        return hit, '没有人框，高宽比算不出来'
    ratio_text = f"人框高/宽 {ratio:.2f}，前提阈值 {ratio_gate:.2f}"
    if ratio < ratio_gate:
        return hit, ratio_text + '，未达到，不再看腿'
    legs = '；'.join(
        _format_leg(
            kps, label, knee_angle, knee_indexes, knee_gate, hip_angle, hip_indexes, hip_gate,
        )
        for (label, knee_angle, knee_indexes), (_hip_label, hip_angle, hip_indexes) in zip(
            _leg_angles(kps), _hip_angles(kps),
        )
    )
    return hit, ratio_text + '。' + legs


def _explain_glasses_pose(kps, spec):
    try:
        ratio = float((spec or {}).get('ear_dist_ratio', 0.28))
    except (TypeError, ValueError):
        ratio = 0.28
    hit = kps is not None and is_wrist_near_ear(kps, ratio)
    if kps is None:
        return False, '没有关键点'
    if not (_kp_ok(kps, L_EAR) or _kp_ok(kps, R_EAR)):
        return hit, '两耳都不可用，无法判断手腕是否靠近耳朵'
    parts = []
    for index, name in ((L_WRIST, '左腕'), (R_WRIST, '右腕')):
        if not _kp_ok(kps, index):
            parts.append(f"{name}不可用")
    if not parts:
        parts.append('双腕都有')
    return hit, f"镜脚触碰看手腕到耳的距离，阈值 {ratio:.2f} 个肩宽。" + '，'.join(parts)


def _explain_watch_pose(kps, spec):
    if kps is None:
        return False, '没有关键点'
    missing = _missing_names(kps, (L_WRIST, R_WRIST))
    if missing:
        return False, '点击手表需要双手腕，缺 ' + '、'.join(missing)
    try:
        ratio = float((spec or {}).get('watch_dist_ratio', 0.50))
    except (TypeError, ValueError):
        ratio = 0.50
    return False, f"双手腕都有。还要有手表检测框，另一只手腕进入表附近（{ratio:.2f} 个肩宽）才算点击"
