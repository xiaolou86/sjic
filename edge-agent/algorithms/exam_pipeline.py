"""
混合任务：一路视频，按启用场景决定跑目标检测、姿态，或两者。

两者都需要时（含智能眼镜、智能手表），同一帧先检测再姿态。
智能眼镜：眼镜框落在头部区域，且手腕靠近耳朵，才计入触碰。
智能手表：手表框附近另一只手点一下即计入点击，默认 1 次即有作弊嫌疑。
"""
import time
from datetime import datetime

import cv2

from .base import BaseAlgorithm, effective_confidence
from .class_map import apply_model_class_ids
from .detection_preview import offer_detection_preview
from .object_detection import ObjectDetectionAlgorithm
from .occlusion import is_occlusion_spec, occlusion_preview
from .pose_behavior import PoseBehaviorAlgorithm
from .pose_geometry import normalize_mount_position, person_has_glasses
from .rules import behavior_rois, build_rules, explain_detection_rules, person_count_specs
from runtime import create_runtime
from utils.calc import get_letterbox_params, preprocess
from utils.rtsp import FramePump, InferPacer, is_valid_frame
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


_FUSION_TYPES = frozenset({'smart_glasses', 'smart_watch'})


def _boxes_of_classes(boxes, class_ids, min_confidence):
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
            # 遮挡不看检测框，也不吃任务置信度。混进 build_rules 会被当成未知规则丢掉。
            occlusion_specs = [spec for spec in rules_raw if is_occlusion_spec(spec)]
            detect_raw = [spec for spec in rules_raw if not is_occlusion_spec(spec)]
            behaviors = _enabled([
                item for item in (algo_params.get('behaviors') or [])
                if isinstance(item, dict)
                and item.get('type') not in _FUSION_TYPES
            ])
            fusions = _enabled(algo_params.get('fusions'))
            need_od = bool(detect_raw or fusions)
            need_pose = bool(behaviors or fusions)
            if not need_od and not need_pose and not occlusion_specs:
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
                f"occlusion={len(occlusion_specs)} rules={len(detect_raw)} "
                f"behaviors={len(behaviors)} fusions={len(fusions)}"
            )

            infer_fps = float(parameters.get('inferFps') or algo_params.get('infer_fps') or 5)
            rtsp_url = (config_dict.get('camera') or {}).get('rtsp_url')
            view = normalize_mount_position((config_dict.get('camera') or {}).get('mount_position'))
            logger.info(f"Throughput caps: inferFps={infer_fps:.1f}")

            pump = FramePump(camera_stream, stop_event, rtsp_url, logger)
            pump.start()
            first_frame, last_seq = pump.get_latest(last_seq=0, wait_sec=8.0)
            new_h = new_w = top = left = bottom = right = None
            if need_od or need_pose:
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

            for spec in detect_raw:
                spec['_min_confidence'] = effective_confidence(spec, task_confidence)
            rules = build_rules(
                detect_raw,
                transform_roi,
                alert_threshold,
                od_helper.is_point_in_roi,
                logger,
            ) if need_od else []
            occlusion_state = {}

            def emit_occlusion(**kwargs):
                if od_algorithm_id is not None:
                    kwargs['algorithm_id'] = od_algorithm_id
                if on_alert:
                    on_alert(**kwargs)
            person_rules = {
                rule.id: rule
                for rule in build_rules(
                    person_count_specs(behaviors),
                    transform_roi,
                    alert_threshold,
                    None,
                    logger,
                )
            } if need_pose else {}
            scene_rois = behavior_rois(behaviors, transform_roi) if need_pose else {}

            labelmap = ((config_dict.get('models') or {}).get('object_detection') or {}).get('labelmap')
            apply_model_class_ids(rules, fusions, od_runtime, labelmap, logger)
            infer_classes = []
            for rule in rules:
                infer_classes.extend(rule.class_ids or [])
            for fusion in fusions:
                infer_classes.extend(_class_ids(fusion))
            infer_classes = sorted(set(int(x) for x in infer_classes))
            if not infer_classes and rules:
                infer_classes = [0]
                logger.warning(
                    "检测场景没有类别，推理只保留类别 0。"
                    "眼镜、手表若不是类别 0，画面上不会有框"
                )
            elif infer_classes:
                logger.info(f"object classes={infer_classes}")

            od_conf_specs = detect_raw + fusions
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

            warmup = first_frame if (need_od or need_pose) and is_valid_frame(first_frame) else None
            if warmup is not None and new_h is not None:
                processed = preprocess(warmup, new_h, new_w, top, bottom, left, right)
                if processed is not None:
                    self._warmup(od_runtime, processed, od_confidence, infer_classes, logger, 'od')
                    self._warmup(pose_runtime, processed, pose_confidence, None, logger, 'pose')

            frame_idx = 0
            last_log = time.time()
            fps_window_t = time.time()
            fps_window_n = 0
            pacer = InferPacer(infer_fps)
            while pacer.wait(stop_event):
                frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                if stop_event.is_set():
                    break
                if frame is None or not is_valid_frame(frame):
                    continue
                now = datetime.now()
                if occlusion_specs:
                    od_helper._check_occlusion(
                        occlusion_specs, occlusion_state, frame, now,
                        task_sched_start, task_sched_end, alert_threshold,
                        emit_occlusion, task_name, logger,
                    )
                occlusion_view = occlusion_preview(occlusion_specs, occlusion_state, now) if occlusion_specs else None
                if not need_od and not need_pose:
                    offer_detection_preview(
                        config_dict.get('task_id'),
                        frame,
                        occlusion=occlusion_view,
                    )
                    continue
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

                scenes = []
                if od_ok:
                    try:
                        scenes.extend(explain_detection_rules(
                            rules, boxes, now, task_sched_start, task_sched_end,
                        ))
                    except Exception as e:
                        logger.debug(f"detection preview skipped: {e}")
                    self._eval_rules(
                        rules, boxes, now, processed, task_sched_start, task_sched_end,
                        task_name, od_algorithm_id, on_alert, logger,
                    )
                if pose_ok:
                    pose_helper.evaluate_behaviors(
                        behaviors, persons, now, processed, view, task_confidence,
                        task_sched_start, task_sched_end, alert_threshold, task_name,
                        state_since, last_alert, extra_state, person_rules, scene_rois,
                        on_alert, logger, algorithm_id=pose_algorithm_id,
                    )
                if od_ok and pose_ok and fusions:
                    self._eval_fusions(
                        fusions, boxes, persons, now, processed, task_confidence,
                        task_sched_start, task_sched_end, alert_threshold, task_name,
                        pose_algorithm_id or od_algorithm_id, last_alert, extra_state,
                        pose_helper, on_alert, logger,
                    )
                if pose_ok:
                    try:
                        scenes.extend(pose_helper.preview_debug(
                            list(behaviors or []) + list(fusions or []),
                            persons, now, view, task_confidence,
                            task_sched_start, task_sched_end, scene_rois, boxes=boxes,
                        ))
                    except Exception as e:
                        logger.debug(f"preview debug skipped: {e}")
                offer_detection_preview(
                    config_dict.get('task_id'),
                    processed,
                    boxes=boxes if need_od and od_ok else None,
                    persons=persons if need_pose and pose_ok else None,
                    object_threshold=od_confidence if need_od else None,
                    pose_threshold=pose_confidence if need_pose else None,
                    infer_ms=infer_ms,
                    object_error=need_od and not od_ok,
                    pose_error=need_pose and not pose_ok,
                    scenes=scenes,
                    occlusion=occlusion_view,
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

    def _eval_fusions(
        self, fusions, boxes, persons, now, processed, task_confidence,
        task_sched_start, task_sched_end, alert_threshold, task_name,
        algorithm_id, _last_alert, extra_state, pose_helper, on_alert, logger,
    ):
        for spec in fusions:
            btype = spec.get('type')
            if btype not in _FUSION_TYPES:
                logger.warning(f"Unknown fusion scene: {btype}")
                continue
            bid = spec.get('id') or btype
            if not is_item_active_now(now, spec, task_sched_start, task_sched_end):
                extra_state[bid] = {}
                pose_helper._person_tracker.clear_behavior(bid)
                continue
            scene_conf = effective_confidence(spec, task_confidence)
            target_boxes = _boxes_of_classes(boxes, _class_ids(spec), scene_conf)
            persons_for_spec = [
                (box, kps) for box, kps in persons
                if box is None or float(getattr(box, 'confidence', 0) or 0) >= scene_conf
            ]
            if btype == 'smart_glasses':
                wearing = [
                    (box, kps) for box, kps in persons_for_spec
                    if person_has_glasses(box, kps, target_boxes)
                ]
                hits = pose_helper._glasses_hits(wearing, spec, bid, now, logger)
                message = (
                    f"行为[{spec.get('name') or 'smart_glasses'}] "
                    f"检出眼镜且镜脚触碰达 {spec.get('min_touches', 3)} 次"
                )
                matched = wearing
            else:
                hits = pose_helper._watch_hits(
                    persons_for_spec, target_boxes, spec, bid, now, logger
                )
                clicks = spec.get('min_touches', 1)
                message = (
                    f"行为[{spec.get('name') or 'smart_watch'}] "
                    f"检出手表且手指点击达 {clicks} 次"
                )
                matched = persons_for_spec
            for box, kps, track in hits:
                pose_helper.emit_pose_alert(
                    spec, btype, bid, (box, kps), message, matched, processed,
                    now, alert_threshold, task_name, algorithm_id, track.last_alert, track.since,
                    on_alert, logger, extra_boxes=target_boxes,
                )
