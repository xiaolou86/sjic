"""
驾考混合任务：一路视频，按启用场景决定跑目标检测、姿态，或两者。

两者都需要时（含智能眼镜），同一帧先检测再姿态。
智能眼镜：眼镜框落在头部区域，且手腕靠近耳朵，才计入触碰。
"""
import time
from datetime import datetime

import cv2

from .base import BaseAlgorithm, effective_confidence
from .object_detection import ObjectDetectionAlgorithm
from .pose_behavior import (
    POINTWISE_TYPES,
    PoseBehaviorAlgorithm,
    _eval_behavior,
)
from .pose_geometry import normalize_mount_position, person_has_glasses
from .rules import build_rules
from runtime import create_runtime
from utils.calc import get_letterbox_params, preprocess
from utils.rtsp import FramePump, is_valid_frame
from utils.schedule import is_item_active_now


def _enabled(items):
    return [
        item for item in (items or [])
        if isinstance(item, dict) and item.get('enabled', True) is not False
    ]


def _class_ids(spec):
    ids = []
    for raw in spec.get('class_ids') or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _glasses_boxes(boxes, class_ids, min_confidence):
    wanted = set(class_ids)
    if not wanted:
        return []
    matched = []
    for box in boxes or []:
        try:
            if int(getattr(box, 'class_id', -1)) not in wanted:
                continue
            if float(getattr(box, 'confidence', 0) or 0) < float(min_confidence):
                continue
        except (TypeError, ValueError):
            continue
        matched.append(box)
    return matched


class ExamPipelineAlgorithm(BaseAlgorithm):
    """同一帧上按场景组合目标检测与姿态。本任务自建 runtime，不使用全局共享会话。"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        od_runtime = None
        pose_runtime = None
        pump = None
        try:
            parameters = config_dict.get('parameters') or {}
            algo_params = parameters.get('algorithm_parameters') or {}
            task_confidence = float(parameters.get('confidence', 0.5))
            alert_threshold = int(parameters.get('alertThreshold', 10))
            task_name = config_dict.get('task_id', 'unknown_task')
            task_sched_start = parameters.get('schedule_start') or algo_params.get('schedule_start')
            task_sched_end = parameters.get('schedule_end') or algo_params.get('schedule_end')

            rules_raw = _enabled(algo_params.get('rules'))
            behaviors = _enabled([
                item for item in (algo_params.get('behaviors') or [])
                if isinstance(item, dict) and item.get('type') != 'smart_glasses'
            ])
            fusions = _enabled(algo_params.get('fusions'))
            need_od = bool(rules_raw or fusions)
            need_pose = bool(behaviors or fusions)
            if not need_od and not need_pose:
                raise RuntimeError("exam_pipeline: no enabled scenes")
            if camera_stream is None:
                raise RuntimeError("exam_pipeline: camera is None")

            paths = config_dict.get('model_local_paths') or {}
            od_path = paths.get('object_detection')
            pose_path = paths.get('pose_behavior')
            if need_od and not od_path:
                raise RuntimeError("exam_pipeline: object detection model missing")
            if need_pose and not pose_path:
                raise RuntimeError("exam_pipeline: pose model missing")

            models_meta = config_dict.get('models') or {}
            od_algorithm_id = (models_meta.get('object_detection') or {}).get('algorithm_id')
            pose_algorithm_id = (models_meta.get('pose_behavior') or {}).get('algorithm_id')

            architecture = config_dict.get('architecture') or 'x86'
            if need_od:
                od_runtime = create_runtime(architecture)
                od_runtime.load(od_path)
            if need_pose:
                pose_runtime = create_runtime(architecture)
                pose_runtime.load(pose_path)
            logger.info(
                f"exam_pipeline plan: od={need_od} pose={need_pose} "
                f"rules={len(rules_raw)} behaviors={len(behaviors)} fusions={len(fusions)}"
            )

            infer_fps = float(parameters.get('inferFps') or algo_params.get('infer_fps') or 5)
            infer_interval = (1.0 / infer_fps) if infer_fps > 0 else 0.0
            decode_fps = infer_fps if infer_fps > 0 else 12.0
            rtsp_url = (config_dict.get('camera') or {}).get('rtsp_url')
            view = normalize_mount_position((config_dict.get('camera') or {}).get('mount_position'))

            pump = FramePump(camera_stream, stop_event, rtsp_url, logger, max_decode_fps=decode_fps)
            pump.start()
            first_frame, last_seq = pump.get_latest(last_seq=0, wait_sec=8.0)
            if first_frame is None:
                h = camera_stream.get(cv2.CAP_PROP_FRAME_HEIGHT)
                w = camera_stream.get(cv2.CAP_PROP_FRAME_WIDTH)
            else:
                h, w = first_frame.shape[0], first_frame.shape[1]
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            if new_h is None:
                logger.error("error: get_letterbox_params return None")
                return

            od_helper = ObjectDetectionAlgorithm()
            pose_helper = PoseBehaviorAlgorithm()

            def transform_roi(region):
                return od_helper._transform_roi(region, new_h, new_w, top, left, logger)

            for spec in rules_raw:
                spec['_min_confidence'] = effective_confidence(spec, task_confidence)
            rules = build_rules(
                rules_raw,
                transform_roi,
                alert_threshold,
                od_helper.is_point_in_roi,
                logger,
            ) if need_od else []

            infer_classes = []
            for rule in rules:
                infer_classes.extend(rule.class_ids or [])
            for fusion in fusions:
                infer_classes.extend(_class_ids(fusion))
            infer_classes = sorted(set(int(x) for x in infer_classes))
            if not infer_classes and rules:
                infer_classes = [0]

            od_conf_specs = rules_raw + fusions
            pose_conf_specs = behaviors + fusions
            od_confidence = min(
                (effective_confidence(spec, task_confidence) for spec in od_conf_specs),
                default=task_confidence,
            ) if od_conf_specs else task_confidence
            pose_confidence = min(
                (effective_confidence(spec, task_confidence) for spec in pose_conf_specs),
                default=task_confidence,
            ) if pose_conf_specs else task_confidence

            state_since = {b.get('id') or b.get('type'): None for b in behaviors}
            last_alert = {}
            for spec in behaviors + fusions:
                last_alert[spec.get('id') or spec.get('type')] = None
            extra_state = {spec.get('id') or spec.get('type'): {} for spec in behaviors + fusions}

            warmup = first_frame if is_valid_frame(first_frame) else None
            if warmup is not None:
                processed = preprocess(warmup, new_h, new_w, top, bottom, left, right)
                if processed is not None:
                    self._warmup(od_runtime, processed, od_confidence, infer_classes, logger, 'od')
                    self._warmup(pose_runtime, processed, pose_confidence, None, logger, 'pose')

            frame_idx = 0
            last_log = time.time()
            fps_window_t = time.time()
            fps_window_n = 0
            next_infer_t = 0.0
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
                boxes = []
                od_ok = False
                if od_runtime is not None:
                    try:
                        boxes = od_runtime.infer(
                            processed, conf=od_confidence, classes=infer_classes or None, imgsz=640
                        ).boxes or []
                        od_ok = True
                    except Exception as e:
                        logger.warning(f"object detection infer skipped: {e}")

                persons = []
                pose_ok = False
                if pose_runtime is not None:
                    try:
                        pose_result = pose_runtime.infer(
                            processed, conf=pose_confidence, classes=None, imgsz=640
                        )
                        persons = pose_helper._extract_persons(pose_result, logger)
                        pose_ok = True
                    except Exception as e:
                        logger.warning(f"pose infer skipped: {e}")
                infer_ms = (time.time() - t0) * 1000

                frame_idx += 1
                fps_window_n += 1
                if frame_idx == 1 or time.time() - last_log >= 5:
                    dt = max(time.time() - fps_window_t, 1e-6)
                    logger.info(
                        f"Frame #{frame_idx} process={fps_window_n / dt:.1f}fps "
                        f"infer={infer_ms:.0f}ms boxes={len(boxes)} persons={len(persons)} "
                        f"od={need_od} pose={need_pose}"
                    )
                    last_log = time.time()
                    fps_window_t = last_log
                    fps_window_n = 0

                now = datetime.now()
                if od_ok:
                    self._eval_rules(
                        rules, boxes, now, processed, task_sched_start, task_sched_end,
                        task_name, od_algorithm_id, on_alert, logger,
                    )
                if pose_ok:
                    self._eval_behaviors(
                        behaviors, persons, now, processed, view, task_confidence,
                        task_sched_start, task_sched_end, alert_threshold, task_name,
                        pose_algorithm_id, state_since, last_alert, extra_state,
                        pose_helper, on_alert, logger,
                    )
                if od_ok and pose_ok and fusions:
                    self._eval_fusions(
                        fusions, boxes, persons, now, processed, task_confidence,
                        task_sched_start, task_sched_end, alert_threshold, task_name,
                        pose_algorithm_id or od_algorithm_id, last_alert, extra_state,
                        pose_helper, on_alert, logger,
                    )
        except Exception as e:
            logger.error(f"Error in exam_pipeline: {str(e)}", exc_info=True)
            raise
        finally:
            if pump is not None:
                pump.release()
            for runtime_obj in (od_runtime, pose_runtime):
                if runtime_obj is None:
                    continue
                try:
                    runtime_obj.release()
                except Exception:
                    pass

    def _warmup(self, runtime_obj, processed, confidence, classes, logger, label):
        if runtime_obj is None:
            return
        try:
            runtime_obj.infer(processed, conf=confidence, classes=classes, imgsz=640)
            logger.info(f"Warmup {label} infer done")
        except Exception as e:
            logger.warning(f"Warmup {label} infer failed: {e}")

    def _eval_rules(
        self, rules, boxes, now, processed, task_sched_start, task_sched_end,
        task_name, algorithm_id, on_alert, logger,
    ):
        for rule in rules:
            if not is_item_active_now(now, rule.spec, task_sched_start, task_sched_end):
                rule._state_since = None
                continue
            hit = rule.evaluate(boxes, now, logger)
            if not hit or not on_alert:
                continue
            message = (
                f"规则[{hit['rule_name']}] {hit['alert_type']} "
                f"目标数={len(hit['boxes'])} 置信度={hit['confidence']:.2f}"
            )
            alert_frame = self.draw_alert_overlay(
                processed,
                boxes=hit['boxes'],
                roi_points=rule.roi_points,
                caption=message,
            )
            logger.info(f"Triggering alert {hit['alert_type']} for {task_name} rule={hit['rule_id']}")
            on_alert(
                alert_type=hit['alert_type'],
                confidence=hit['confidence'],
                image_frame=alert_frame,
                message=message,
                raw_frame=processed,
                algorithm_id=algorithm_id,
            )

    def _eval_behaviors(
        self, behaviors, persons, now, processed, view, task_confidence,
        task_sched_start, task_sched_end, alert_threshold, task_name,
        algorithm_id, state_since, last_alert, extra_state, pose_helper, on_alert, logger,
    ):
        for spec in behaviors:
            bid = spec.get('id') or spec.get('type')
            btype = spec.get('type')
            if not is_item_active_now(now, spec, task_sched_start, task_sched_end):
                state_since[bid] = None
                extra_state[bid] = {}
                continue

            scene_conf = effective_confidence(spec, task_confidence)
            persons_for_spec = [
                (box, kps) for box, kps in persons
                if box is None or float(getattr(box, 'confidence', 0) or 0) >= scene_conf
            ]
            hit_person = None
            message = None

            if btype == 'invigilator_absent':
                ok, box, standing_n = pose_helper._eval_invigilator_absent(
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
            else:
                continue

            self._emit_pose_alert(
                spec, btype, bid, hit_person, message, persons_for_spec, processed,
                now, alert_threshold, task_name, algorithm_id, last_alert, state_since,
                on_alert, logger,
            )

    def _eval_fusions(
        self, fusions, boxes, persons, now, processed, task_confidence,
        task_sched_start, task_sched_end, alert_threshold, task_name,
        algorithm_id, last_alert, extra_state, pose_helper, on_alert, logger,
    ):
        for spec in fusions:
            if spec.get('type') != 'smart_glasses':
                logger.warning(f"Unknown fusion scene: {spec.get('type')}")
                continue
            bid = spec.get('id') or spec.get('type')
            if not is_item_active_now(now, spec, task_sched_start, task_sched_end):
                extra_state[bid] = {}
                continue
            scene_conf = effective_confidence(spec, task_confidence)
            glasses = _glasses_boxes(boxes, _class_ids(spec), scene_conf)
            wearing = []
            for box, kps in persons:
                if box is not None and float(getattr(box, 'confidence', 0) or 0) < scene_conf:
                    continue
                if person_has_glasses(box, kps, glasses):
                    wearing.append((box, kps))
            ok, box, kps = pose_helper._eval_smart_glasses(wearing, spec, extra_state[bid], now)
            if not ok:
                continue
            message = (
                f"行为[{spec.get('name') or 'smart_glasses'}] "
                f"检出眼镜且镜脚触碰达 {spec.get('min_touches', 3)} 次"
            )
            self._emit_pose_alert(
                spec, 'smart_glasses', bid, (box, kps), message, wearing, processed,
                now, alert_threshold, task_name, algorithm_id, last_alert, {},
                on_alert, logger, extra_boxes=glasses,
            )

    def _emit_pose_alert(
        self, spec, btype, bid, hit_person, message, persons_for_spec, processed,
        now, alert_threshold, task_name, algorithm_id, last_alert, state_since,
        on_alert, logger, extra_boxes=None,
    ):
        if hit_person is None or not on_alert:
            return
        la = last_alert.get(bid)
        if la and (now - la).total_seconds() < alert_threshold:
            return
        box, kps = hit_person
        if btype == 'invigilator_absent':
            skeletons = [pk for _, pk in persons_for_spec if pk is not None]
        elif kps is not None:
            skeletons = [kps]
        else:
            skeletons = None
        draw_boxes = []
        if box is not None:
            draw_boxes.append(box)
        for extra in extra_boxes or []:
            if extra is not box:
                draw_boxes.append(extra)
        alert_frame = self.draw_alert_overlay(
            processed,
            boxes=draw_boxes or None,
            caption=message or f"行为[{spec.get('name') or btype}]",
            skeletons=skeletons,
        )
        logger.info(f"Triggering {spec.get('alert_type') or btype} for {task_name}")
        on_alert(
            alert_type=spec.get('alert_type') or btype,
            confidence=float(getattr(box, 'confidence', 1.0) or 1.0) if box else 1.0,
            image_frame=alert_frame,
            message=message,
            raw_frame=processed,
            algorithm_id=algorithm_id,
        )
        last_alert[bid] = now
        if btype not in ('smart_glasses', 'invigilator_absent') and bid in state_since:
            state_since[bid] = now
