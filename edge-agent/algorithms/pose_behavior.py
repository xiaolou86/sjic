"""
姿态行为引擎：张望 / 低头 / 不看屏幕 / 手托下巴 / 倒地 / 手指屏幕。

依赖姿态模型（YOLO-Pose 等）经 runtime.infer 返回 keypoints。
若当前 runtime 仅返回 boxes，则退化为「有人框 + 宽高比/位置」粗判，并在日志中提示。
"""
from .base import BaseAlgorithm
import math
from datetime import datetime
from utils.calc import get_letterbox_params, preprocess
from utils.rtsp import FramePump, is_valid_frame


# COCO 17 keypoints 索引
NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16


def _kp_ok(kps, idx, min_conf=0.25):
    if kps is None or idx >= len(kps):
        return False
    x, y, c = kps[idx]
    return c >= min_conf and x > 0 and y > 0


def _kp(kps, idx):
    return kps[idx][0], kps[idx][1]


def estimate_yaw_pitch(kps):
    """粗略 yaw/pitch（度）。正 yaw=左转脸，正 pitch=低头倾向。"""
    if not (_kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER) and _kp_ok(kps, NOSE)):
        return None, None
    ls = _kp(kps, L_SHOULDER)
    rs = _kp(kps, R_SHOULDER)
    nose = _kp(kps, NOSE)
    mid_x = (ls[0] + rs[0]) / 2.0
    mid_y = (ls[1] + rs[1]) / 2.0
    shoulder_w = max(abs(rs[0] - ls[0]), 1.0)
    # yaw：鼻相对肩中线的水平偏移 / 肩宽
    yaw = max(-90.0, min(90.0, ((nose[0] - mid_x) / shoulder_w) * 90.0))
    # pitch：鼻相对肩中线的竖直偏移（向下为正）
    pitch = max(-90.0, min(90.0, ((nose[1] - mid_y) / shoulder_w) * 90.0))
    return yaw, pitch


def is_looking_aside(kps, yaw_degrees=45):
    yaw, _ = estimate_yaw_pitch(kps)
    if yaw is None:
        return False
    return abs(yaw) >= float(yaw_degrees)


def is_head_down(kps, pitch_degrees=30):
    _, pitch = estimate_yaw_pitch(kps)
    if pitch is None:
        return False
    return pitch >= float(pitch_degrees)


def is_gaze_away(kps, yaw_degrees=25, pitch_degrees=25):
    """不看屏幕：偏头或低头超过阈值。"""
    yaw, pitch = estimate_yaw_pitch(kps)
    if yaw is None:
        return False
    return abs(yaw) >= float(yaw_degrees) or pitch >= float(pitch_degrees)


def is_chin_rest(kps):
    """手腕靠近下颌（鼻/嘴附近）。"""
    if not _kp_ok(kps, NOSE):
        return False
    nose = _kp(kps, NOSE)
    for wi in (L_WRIST, R_WRIST):
        if not _kp_ok(kps, wi):
            continue
        wx, wy = _kp(kps, wi)
        # 相对肩宽归一
        if _kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER):
            sw = max(abs(_kp(kps, R_SHOULDER)[0] - _kp(kps, L_SHOULDER)[0]), 1.0)
        else:
            sw = 80.0
        dist = math.hypot(wx - nose[0], wy - nose[1]) / sw
        if dist < 0.55 and wy >= nose[1] - 0.2 * sw:
            return True
    return False


def is_fall(kps, box=None):
    """倒地：肩-髋连线接近水平，或检测框宽高比偏大且重心偏低。"""
    if _kp_ok(kps, L_SHOULDER) and _kp_ok(kps, R_SHOULDER) and _kp_ok(kps, L_HIP) and _kp_ok(kps, R_HIP):
        sy = (_kp(kps, L_SHOULDER)[1] + _kp(kps, R_SHOULDER)[1]) / 2.0
        hy = (_kp(kps, L_HIP)[1] + _kp(kps, R_HIP)[1]) / 2.0
        sx = (_kp(kps, L_SHOULDER)[0] + _kp(kps, R_SHOULDER)[0]) / 2.0
        hx = (_kp(kps, L_HIP)[0] + _kp(kps, R_HIP)[0]) / 2.0
        dx, dy = abs(hx - sx), abs(hy - sy)
        if dx > 1 and dy / max(dx, 1.0) < 0.45:
            return True
    if box is not None:
        w = max(float(box.x2 - box.x1), 1.0)
        h = max(float(box.y2 - box.y1), 1.0)
        if w / h > 1.35:
            return True
    return False


def is_finger_point(kps, require_standing=True):
    """站立 + 手腕明显高于肘（伸臂指向）。"""
    standing = True
    if require_standing and _kp_ok(kps, L_HIP) and _kp_ok(kps, L_ANKLE):
        standing = _kp(kps, L_ANKLE)[1] > _kp(kps, L_HIP)[1] + 20
    if require_standing and not standing:
        return False
    for elbow, wrist in ((L_ELBOW, L_WRIST), (R_ELBOW, R_WRIST)):
        if _kp_ok(kps, elbow) and _kp_ok(kps, wrist):
            if _kp(kps, wrist)[1] < _kp(kps, elbow)[1] - 15:
                return True
    return False


BEHAVIOR_EVALUATORS = {
    'gaze_away': lambda kps, box, spec: is_gaze_away(
        kps, spec.get('yaw_degrees', 25), spec.get('pitch_degrees', 25)
    ),
    'look_aside': lambda kps, box, spec: is_looking_aside(kps, spec.get('yaw_degrees', 45)),
    'head_down': lambda kps, box, spec: is_head_down(kps, spec.get('pitch_degrees', 30)),
    'chin_rest': lambda kps, box, spec: is_chin_rest(kps),
    'fall': lambda kps, box, spec: is_fall(kps, box),
    'finger_point': lambda kps, box, spec: is_finger_point(
        kps, bool(spec.get('require_standing', True))
    ),
}


class PoseBehaviorAlgorithm(BaseAlgorithm):
    """一次姿态推理，多条行为规则计时告警。"""

    def _extract_persons(self, result, logger):
        """从 DetectionResult 提取 (box, keypoints[17][3]) 列表。"""
        persons = []
        boxes = getattr(result, 'boxes', None) or []
        keypoints = getattr(result, 'keypoints', None)
        if keypoints is None and hasattr(result, '_raw') and result._raw is not None:
            try:
                raw = result._raw[0] if isinstance(result._raw, list) else result._raw
                if hasattr(raw, 'keypoints') and raw.keypoints is not None:
                    kpdata = raw.keypoints.data
                    if hasattr(kpdata, 'cpu'):
                        kpdata = kpdata.cpu().numpy()
                    for i, box in enumerate(boxes):
                        kps = kpdata[i] if i < len(kpdata) else None
                        persons.append((box, kps))
                    return persons
            except Exception as e:
                logger.debug(f"keypoints from raw failed: {e}")

        if keypoints is not None:
            for i, box in enumerate(boxes):
                kps = keypoints[i] if i < len(keypoints) else None
                persons.append((box, kps))
            return persons

        # 无关键点：仅 boxes，行为判定能力受限
        for box in boxes:
            persons.append((box, None))
        return persons

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        try:
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            algo_params = parameters.get('algorithm_parameters') or {}
            confidence = float(parameters.get('confidence', 0.5))
            alert_threshold = int(parameters.get('alertThreshold', 10))
            behaviors = [b for b in (algo_params.get('behaviors') or []) if b.get('enabled', True)]
            task_name = config_dict.get('task_id', 'unknown_task')

            if not behaviors:
                logger.warning("pose_behavior: no behaviors configured")
                return
            if camera_stream is None:
                logger.error("error: camera is None")
                return

            rtsp_url = config_dict.get('camera', {}).get('rtsp_url')
            pump = FramePump(camera_stream, stop_event, rtsp_url, logger)
            pump.start()
            try:
                runtime.load(model_path)
                first_frame, last_seq = pump.get_latest(last_seq=0, wait_sec=8.0)
                if first_frame is None:
                    import cv2
                    h, w = camera_stream.get(cv2.CAP_PROP_FRAME_HEIGHT), camera_stream.get(cv2.CAP_PROP_FRAME_WIDTH)
                else:
                    h, w = first_frame.shape[0], first_frame.shape[1]
                new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
                if new_h is None:
                    logger.error("error: get_letterbox_params return None")
                    return

                state_since = {b.get('id') or b.get('type'): None for b in behaviors}
                last_alert = {b.get('id') or b.get('type'): None for b in behaviors}

                while not stop_event.is_set():
                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if stop_event.is_set():
                        break
                    if frame is None or not is_valid_frame(frame):
                        continue
                    processed = preprocess(frame, new_h, new_w, top, bottom, left, right)
                    if processed is None:
                        continue
                    try:
                        result = runtime.infer(processed, conf=confidence, classes=None, imgsz=640)
                    except Exception as e:
                        logger.warning(f"pose infer skipped: {e}")
                        continue

                    persons = self._extract_persons(result, logger)
                    now = datetime.now()

                    for spec in behaviors:
                        bid = spec.get('id') or spec.get('type')
                        btype = spec.get('type')
                        evaluator = BEHAVIOR_EVALUATORS.get(btype)
                        if not evaluator:
                            continue
                        seconds = float(spec.get('seconds', 3))
                        alert_type = spec.get('alert_type') or btype
                        hit_person = None
                        for box, kps in persons:
                            if kps is None and btype not in ('fall',):
                                continue
                            try:
                                if evaluator(kps, box, spec):
                                    hit_person = (box, kps)
                                    break
                            except Exception as e:
                                logger.debug(f"behavior {btype} eval error: {e}")

                        if hit_person is None:
                            state_since[bid] = None
                            continue
                        if state_since[bid] is None:
                            state_since[bid] = now
                            continue
                        elapsed = (now - state_since[bid]).total_seconds()
                        if elapsed < seconds:
                            continue
                        la = last_alert[bid]
                        if la and (now - la).total_seconds() < alert_threshold:
                            continue

                        box, _ = hit_person
                        message = f"行为[{spec.get('name') or btype}] 持续 {elapsed:.1f}s"
                        alert_frame = self.draw_alert_overlay(
                            processed,
                            boxes=[box] if box is not None else None,
                            caption=message,
                        )
                        logger.info(f"Triggering {alert_type} for {task_name}")
                        if on_alert:
                            on_alert(
                                alert_type=alert_type,
                                confidence=float(getattr(box, 'confidence', 1.0) or 1.0),
                                image_frame=alert_frame,
                                message=message,
                            )
                        last_alert[bid] = now
                        state_since[bid] = now
            finally:
                pump.release()
        except Exception as e:
            logger.error(f"Error in pose_behavior: {str(e)}", exc_info=True)
            raise
