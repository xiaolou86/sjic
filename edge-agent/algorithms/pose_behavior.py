"""
姿态行为引擎：张望 / 低头 / 不看屏幕 / 手托下巴 / 手指屏幕 /
捂嘴报题 / AI 智能眼镜 / 考试员不巡场。

依赖姿态模型（YOLO-Pose 等）经 runtime.infer 返回 keypoints。
几何判断按摄像头 mount_position（前/后/侧/正上方）切换，避免把俯视看屏判成违规。
若当前 runtime 仅返回 boxes，则跳过关键点行为，并在日志中提示。
"""
from .base import BaseAlgorithm, effective_confidence
from .pose_geometry import (
    is_chin_rest,
    is_cover_mouth,
    is_finger_point,
    is_gaze_away,
    is_head_down,
    is_looking_aside,
    is_standing,
    is_wrist_near_ear,
    normalize_mount_position,
)
import time
from datetime import datetime
from utils.calc import get_letterbox_params, preprocess
from utils.rtsp import FramePump, is_valid_frame
from utils.schedule import is_item_active_now


def _eval_behavior(btype, kps, box, spec, view):
    if btype == 'gaze_away':
        return is_gaze_away(
            kps, spec.get('yaw_degrees', 25), spec.get('pitch_degrees', 25), view
        )
    if btype == 'look_aside':
        return is_looking_aside(kps, spec.get('yaw_degrees', 45), view)
    if btype == 'head_down':
        return is_head_down(kps, spec.get('pitch_degrees', 30), view)
    if btype == 'chin_rest':
        return is_chin_rest(kps, view)
    if btype == 'cover_mouth':
        return is_cover_mouth(kps, view)
    if btype == 'finger_point':
        return is_finger_point(kps, bool(spec.get('require_standing', True)), view)
    return False


POINTWISE_TYPES = frozenset({
    'gaze_away', 'look_aside', 'head_down', 'chin_rest',
    'cover_mouth', 'finger_point',
})
STATEFUL_BEHAVIORS = frozenset({'smart_glasses', 'invigilator_absent'})


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

        for box in boxes:
            persons.append((box, None))
        return persons

    def _eval_smart_glasses(self, persons, spec, state, now):
        """
        手腕靠近耳朵计为一次接触；离开后再靠近累加次数。
        在 seconds 窗口内达到 min_touches 则触发。
        """
        min_touches = int(spec.get('min_touches', 3))
        window = float(spec.get('seconds', 30))
        near = False
        hit_box = None
        for box, kps in persons:
            if kps is None:
                continue
            if is_wrist_near_ear(kps, spec.get('ear_dist_ratio', 0.28)):
                near = True
                hit_box = box
                break

        if near and not state.get('near'):
            state['touches'] = int(state.get('touches') or 0) + 1
            state['window_start'] = state.get('window_start') or now
        if not near:
            state['near'] = False
        else:
            state['near'] = True

        ws = state.get('window_start')
        if ws and (now - ws).total_seconds() > window:
            state['touches'] = 1 if near else 0
            state['window_start'] = now if near else None

        if int(state.get('touches') or 0) >= min_touches:
            state['touches'] = 0
            state['window_start'] = None
            state['near'] = False
            return True, hit_box
        return False, None

    def _eval_invigilator_absent(self, persons, spec, state, now, view):
        """站立人数持续少于 min_standing 达到 seconds（默认 120s）则告警。"""
        min_standing = int(spec.get('min_standing', 2))
        seconds = float(spec.get('seconds', 120))
        standing_n = 0
        sample_box = None
        for box, kps in persons:
            if kps is None:
                if box is not None and is_standing(None, box, view):
                    standing_n += 1
                    sample_box = sample_box or box
                continue
            if is_standing(kps, box, view):
                standing_n += 1
                sample_box = sample_box or box

        if standing_n >= min_standing:
            state['since'] = None
            return False, None, standing_n

        if state.get('since') is None:
            state['since'] = now
            return False, None, standing_n

        elapsed = (now - state['since']).total_seconds()
        if elapsed < seconds:
            return False, None, standing_n
        state['since'] = now
        return True, sample_box, standing_n

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        try:
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            algo_params = parameters.get('algorithm_parameters') or {}
            task_confidence = float(parameters.get('confidence', 0.5))
            confidence = min(
                (effective_confidence(b, task_confidence) for b in behaviors),
                default=task_confidence,
            )
            alert_threshold = int(parameters.get('alertThreshold', 10))
            behaviors = [b for b in (algo_params.get('behaviors') or []) if b.get('enabled', True)]
            task_name = config_dict.get('task_id', 'unknown_task')
            task_sched_start = parameters.get('schedule_start') or algo_params.get('schedule_start')
            task_sched_end = parameters.get('schedule_end') or algo_params.get('schedule_end')

            if not behaviors:
                logger.warning("pose_behavior: no behaviors configured")
                return
            if camera_stream is None:
                logger.error("error: camera is None")
                return

            rtsp_url = config_dict.get('camera', {}).get('rtsp_url')
            view = normalize_mount_position(
                (config_dict.get('camera') or {}).get('mount_position')
            )
            infer_fps = float(
                parameters.get('inferFps')
                or algo_params.get('infer_fps')
                or 5
            )
            infer_interval = (1.0 / infer_fps) if infer_fps > 0 else 0.0
            decode_fps = infer_fps if infer_fps > 0 else 12.0
            pump = FramePump(camera_stream, stop_event, rtsp_url, logger, max_decode_fps=decode_fps)
            pump.start()
            try:
                runtime.load(model_path)
                logger.info(
                    f"Throughput caps: inferFps={infer_fps:.1f} decodeFps≈{decode_fps:.1f} "
                    f"mount_position={view}"
                )
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
                extra_state = {b.get('id') or b.get('type'): {} for b in behaviors}
                next_infer_t = 0.0
                frame_idx = 0
                last_log = time.time()
                fps_window_t = time.time()
                fps_window_n = 0

                while not stop_event.is_set():
                    now_t = time.time()
                    if infer_interval and now_t < next_infer_t:
                        if stop_event.wait(timeout=min(0.05, next_infer_t - now_t)):
                            break
                        continue

                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if stop_event.is_set():
                        break
                    if frame is None or not is_valid_frame(frame):
                        continue
                    next_infer_t = time.time() + infer_interval
                    processed = preprocess(frame, new_h, new_w, top, bottom, left, right)
                    if processed is None:
                        continue
                    t0 = time.time()
                    try:
                        result = runtime.infer(processed, conf=confidence, classes=None, imgsz=640)
                    except Exception as e:
                        logger.warning(f"pose infer skipped: {e}")
                        continue
                    infer_ms = (time.time() - t0) * 1000
                    frame_idx += 1
                    fps_window_n += 1
                    if frame_idx == 1 or time.time() - last_log >= 5:
                        dt = max(time.time() - fps_window_t, 1e-6)
                        logger.info(
                            f"Frame #{frame_idx} process={fps_window_n / dt:.1f}fps "
                            f"infer={infer_ms:.0f}ms behaviors={len(behaviors)}"
                        )
                        last_log = time.time()
                        fps_window_t = last_log
                        fps_window_n = 0

                    persons = self._extract_persons(result, logger)
                    now = datetime.now()

                    for spec in behaviors:
                        bid = spec.get('id') or spec.get('type')
                        btype = spec.get('type')
                        if not is_item_active_now(now, spec, task_sched_start, task_sched_end):
                            state_since[bid] = None
                            extra_state[bid] = {}
                            continue

                        alert_type = spec.get('alert_type') or btype
                        hit_person = None
                        message = None

                        if btype == 'fall':
                            if not extra_state[bid].get('warned'):
                                logger.warning("人员倒地已改为目标检测场景，姿态任务中的跌倒行为已忽略")
                                extra_state[bid]['warned'] = True
                            continue

                        scene_conf = effective_confidence(spec, task_confidence)
                        persons_for_spec = [
                            (box, kps) for box, kps in persons
                            if box is None or float(getattr(box, 'confidence', 0) or 0) >= scene_conf
                        ]

                        if btype == 'smart_glasses':
                            ok, box = self._eval_smart_glasses(
                                persons_for_spec, spec, extra_state[bid], now
                            )
                            if ok:
                                hit_person = (box, None)
                                message = (
                                    f"行为[{spec.get('name') or btype}] "
                                    f"镜脚触碰达 {spec.get('min_touches', 3)} 次"
                                )
                        elif btype == 'invigilator_absent':
                            ok, box, standing_n = self._eval_invigilator_absent(
                                persons_for_spec, spec, extra_state[bid], now, view
                            )
                            if ok:
                                hit_person = (box, None)
                                message = (
                                    f"行为[{spec.get('name') or btype}] "
                                    f"站立仅 {standing_n} 人（需≥{spec.get('min_standing', 2)}）"
                                )
                        elif btype in POINTWISE_TYPES:
                            seconds = float(spec.get('seconds', 3))
                            for box, kps in persons_for_spec:
                                if kps is None:
                                    continue
                                try:
                                    if _eval_behavior(btype, kps, box, spec, view):
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
                            message = f"行为[{spec.get('name') or btype}] 持续 {elapsed:.1f}s"

                        if hit_person is None:
                            continue
                        la = last_alert[bid]
                        if la and (now - la).total_seconds() < alert_threshold:
                            continue

                        box, _ = hit_person
                        alert_frame = self.draw_alert_overlay(
                            processed,
                            boxes=[box] if box is not None else None,
                            caption=message or f"行为[{spec.get('name') or btype}]",
                        )
                        logger.info(f"Triggering {alert_type} for {task_name}")
                        if on_alert:
                            on_alert(
                                alert_type=alert_type,
                                confidence=float(getattr(box, 'confidence', 1.0) or 1.0) if box else 1.0,
                                image_frame=alert_frame,
                                message=message,
                            )
                        last_alert[bid] = now
                        if btype not in STATEFUL_BEHAVIORS:
                            state_since[bid] = now
            finally:
                pump.release()
        except Exception as e:
            logger.error(f"Error in pose_behavior: {str(e)}", exc_info=True)
            raise
