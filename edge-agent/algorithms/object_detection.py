from .base import BaseAlgorithm, effective_confidence
from .class_map import apply_model_class_ids
from .detection_preview import offer_detection_preview
from .occlusion import is_occlusion_spec, occlusion_preview, update_occlusion
from .rules import build_rules, explain_detection_rules
import cv2
import time
from datetime import datetime
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess
from utils.rtsp import FramePump, InferPacer, is_valid_frame
from utils.schedule import is_item_active_now


class ObjectDetectionAlgorithm(BaseAlgorithm):
    """边缘端目标检测算法：一次推理，按任务规则做驻留/缺席/出现判定。"""

    def _transform_roi(self, detection_region, new_h, new_w, top, left, logger):
        if not detection_region:
            return None
        points = detection_region.get('points') or []
        frame_size = detection_region.get('frame_size') or {}
        if not points or not frame_size.get('height') or not frame_size.get('width'):
            return None
        roi_points = transform_points_from_frontend_to_backend(
            points, frame_size['height'], frame_size['width'], new_h, new_w, top, left
        )
        if roi_points is None:
            logger.error("error: roi_points is None")
            return None
        logger.info(f"Transformed ROI Points for inference: {roi_points}")
        return roi_points

    def _check_occlusion(
        self, specs, states, frame, now, task_start, task_end,
        alert_threshold, on_alert, task_name, logger,
    ):
        """用本帧原图看外圈。不看检测框，也不用补边后的画面。"""
        for spec in specs:
            bid = spec.get('id') or spec.get('type') or 'camera_occlusion'
            state = states.setdefault(bid, {'since': None, 'last_alert': None})
            if not is_item_active_now(now, spec, task_start, task_end):
                state['since'] = None
                state['ratio'] = None
                continue
            message = update_occlusion(spec, frame, now, state, alert_threshold)
            if not message or not on_alert:
                continue
            alert_frame = self.draw_alert_overlay(frame, caption=message)
            logger.info(f"Triggering camera_occlusion for {task_name} rule={bid}")
            on_alert(
                alert_type=spec.get('alert_type') or 'camera_blocked',
                confidence=1.0,
                image_frame=alert_frame,
                message=message,
                raw_frame=frame,
            )

    def _legacy_presence_spec(self, algorithm_parameters):
        """无 rules 但配置了 detection_region 时，按旧行为：区域内出现即告警。"""
        region = algorithm_parameters.get('detection_region')
        if not region:
            return []
        return [{
            'id': 'legacy_presence',
            'type': 'presence',
            'name': '检测区域',
            'enabled': True,
            'alert_type': 'object_detection',
            'class_ids': algorithm_parameters.get('labels') or [0],
            'detection_region': region,
        }]

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        """处理目标检测视频"""
        try:
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            task_name = config_dict.get('task_id', 'unknown_task')
            camera = camera_stream

            logger.debug(f"model_path={model_path} task_name={task_name}")
            rule_summaries = []
            for r in (parameters.get('algorithm_parameters') or {}).get('rules') or []:
                rule_summaries.append({
                    'id': r.get('id'),
                    'type': r.get('type'),
                    'enabled': r.get('enabled', True),
                    'has_roi': bool((r.get('detection_region') or {}).get('points')),
                })
            logger.debug(f"rules={rule_summaries}")

            logger.info(f"Loading model for object_detection via runtime: {model_path}")

            if camera is None:
                logger.error("error: camera is None")
                return

            rtsp_url = config_dict.get('camera', {}).get('rtsp_url')
            task_confidence = float(parameters.get('confidence', 0.5))
            algorithm_parameters = parameters.get('algorithm_parameters') or {}
            alert_threshold = int(parameters.get('alertThreshold', 10))
            task_sched_start = parameters.get('schedule_start') or algorithm_parameters.get('schedule_start')
            task_sched_end = parameters.get('schedule_end') or algorithm_parameters.get('schedule_end')
            # 推理不必跟摄像头满帧率；告警场景默认 5fps
            infer_fps = float(
                parameters.get('inferFps')
                or algorithm_parameters.get('infer_fps')
                or 5
            )

            pump = FramePump(camera, stop_event, rtsp_url, logger)
            pump.start()
            try:
                first_frame, last_seq = pump.get_latest(last_seq=0, wait_sec=8.0)
                if first_frame is None:
                    h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
                else:
                    h, w = first_frame.shape[0], first_frame.shape[1]
                new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)

                raw_rules = algorithm_parameters.get('rules')
                if not raw_rules:
                    raw_rules = self._legacy_presence_spec(algorithm_parameters)
                if not raw_rules:
                    raw_rules = [{
                        'id': 'default_presence',
                        'type': 'presence',
                        'name': '整帧出现',
                        'enabled': True,
                        'alert_type': 'object_detection',
                        'class_ids': algorithm_parameters.get('labels') or [0],
                    }]
                    logger.warning("Task has no rules; fallback to whole-frame presence (add rules in task UI)")

                def transform_roi(region):
                    return self._transform_roi(region, new_h, new_w, top, left, logger)

                active_specs = [
                    spec for spec in raw_rules
                    if isinstance(spec, dict) and spec.get('enabled', True) is not False
                ]
                occlusion_specs = [spec for spec in active_specs if is_occlusion_spec(spec)]
                detect_specs = [spec for spec in active_specs if not is_occlusion_spec(spec)]
                for spec in detect_specs:
                    spec['_min_confidence'] = effective_confidence(spec, task_confidence)
                confidence = min(
                    (spec['_min_confidence'] for spec in detect_specs),
                    default=task_confidence,
                )
                rules = build_rules(
                    detect_specs,
                    transform_roi,
                    alert_threshold,
                    self.is_point_in_roi,
                    logger,
                )
                occlusion_state = {}

                def collect_infer_classes():
                    found = []
                    for rule in rules:
                        found.extend(rule.class_ids or [])
                    if rules and algorithm_parameters.get('labels'):
                        found.extend(int(x) for x in algorithm_parameters.get('labels'))
                    return sorted(set(int(x) for x in found))

                infer_classes = collect_infer_classes()
                if rules and not infer_classes:
                    infer_classes = [0]
                need_infer = bool(rules)
                if need_infer and new_h is None:
                    logger.error("error: get_letterbox_params return None")
                    return

                warmup = first_frame if need_infer and is_valid_frame(first_frame) else None
                if need_infer:
                    runtime.load(model_path)
                    apply_model_class_ids(
                        rules, [], runtime,
                        (config_dict.get('model') or {}).get('labelmap'),
                        logger,
                    )
                    infer_classes = collect_infer_classes()
                    if rules and not infer_classes:
                        infer_classes = [0]
                        logger.warning(
                            "检测场景没有类别，推理只保留类别 0。"
                            "眼镜、手表若不是类别 0，画面上不会有框"
                        )
                    elif infer_classes:
                        logger.info(f"object classes={infer_classes}")
                    logger.info(f"Throughput caps: inferFps={infer_fps:.1f}")
                elif occlusion_specs:
                    logger.info(
                        f"摄像头遮挡挂在本路已解码画面上，本帧不跑检测模型 "
                        f"inferFps={infer_fps:.1f}"
                    )
                if warmup is not None:
                    processed = preprocess(warmup, new_h, new_w, top, bottom, left, right)
                    if processed is not None:
                        logger.info("Warmup infer (may init CUDA/CPU) while RTSP pump keeps reading...")
                        try:
                            runtime.infer(processed, conf=confidence, classes=infer_classes, imgsz=640)
                            logger.info("Warmup infer done")
                        except Exception as e:
                            logger.warning(f"Warmup infer failed: {e}")

                frame_idx = 0
                last_log = time.time()
                fps_window_t = time.time()
                fps_window_n = 0
                pacer = InferPacer(infer_fps)
                while pacer.wait(stop_event):
                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if stop_event.is_set():
                        break
                    if frame is None:
                        logger.warning("No new RTSP frame for 2s")
                        continue

                    now = datetime.now()
                    self._check_occlusion(
                        occlusion_specs, occlusion_state, frame, now,
                        task_sched_start, task_sched_end, alert_threshold,
                        on_alert, task_name, logger,
                    )
                    occlusion_view = occlusion_preview(occlusion_specs, occlusion_state, now)
                    if not need_infer:
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
                    try:
                        result = runtime.infer(processed, conf=confidence, classes=infer_classes, imgsz=640)
                    except Exception as infer_err:
                        logger.warning(f"Infer skipped: {infer_err}")
                        continue
                    infer_ms = (time.time() - t0) * 1000
                    boxes = result.boxes or []
                    frame_idx += 1
                    fps_window_n += 1

                    if frame_idx == 1 or time.time() - last_log >= 5:
                        dt = max(time.time() - fps_window_t, 1e-6)
                        process_fps = fps_window_n / dt
                        logger.info(
                            f"Frame #{frame_idx} process={process_fps:.1f}fps "
                            f"infer={infer_ms:.0f}ms boxes={len(boxes)} rules={len(rules)}"
                        )
                        last_log = time.time()
                        fps_window_t = last_log
                        fps_window_n = 0

                    try:
                        scenes = explain_detection_rules(
                            rules, boxes, now, task_sched_start, task_sched_end,
                        )
                    except Exception as e:
                        logger.debug(f"detection preview skipped: {e}")
                        scenes = []
                    offer_detection_preview(
                        config_dict.get('task_id'),
                        processed,
                        boxes=boxes,
                        object_threshold=confidence,
                        infer_ms=infer_ms,
                        occlusion=occlusion_view,
                        scenes=scenes,
                    )

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
                        )
            finally:
                pump.release()

        except Exception as e:
            logger.error(f"Error in object detection: {str(e)}", exc_info=True)
            raise
