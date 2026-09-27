from .base import BaseAlgorithm, effective_confidence
from .rules import build_rules
import cv2
import time
from datetime import datetime
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess
from utils.rtsp import FramePump, is_valid_frame
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
            # 解码/推理都不必跟摄像头满帧率；告警场景默认 5fps
            infer_fps = float(
                parameters.get('inferFps')
                or algorithm_parameters.get('infer_fps')
                or 5
            )
            infer_interval = (1.0 / infer_fps) if infer_fps > 0 else 0.0
            # 与推理同频即可：更高只会多 decode/copy 又被丢掉
            decode_fps = infer_fps if infer_fps > 0 else 12.0

            pump = FramePump(camera, stop_event, rtsp_url, logger, max_decode_fps=decode_fps)
            pump.start()
            try:
                runtime.load(model_path)
                logger.info(
                    f"Throughput caps: inferFps={infer_fps:.1f} decodeFps≈{decode_fps:.1f}"
                )

                first_frame, last_seq = pump.get_latest(last_seq=0, wait_sec=8.0)
                if first_frame is None:
                    h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
                else:
                    h, w = first_frame.shape[0], first_frame.shape[1]
                new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
                if new_h is None:
                    logger.error("error: get_letterbox_params return None")
                    return

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
                for spec in active_specs:
                    spec['_min_confidence'] = effective_confidence(spec, task_confidence)
                confidence = min(
                    (spec['_min_confidence'] for spec in active_specs),
                    default=task_confidence,
                )
                rules = build_rules(
                    raw_rules,
                    transform_roi,
                    alert_threshold,
                    self.is_point_in_roi,
                    logger,
                )

                infer_classes = []
                for rule in rules:
                    infer_classes.extend(rule.class_ids or [])
                if algorithm_parameters.get('labels'):
                    infer_classes.extend(int(x) for x in algorithm_parameters.get('labels'))
                infer_classes = sorted(set(infer_classes)) or [0]

                warmup = first_frame if is_valid_frame(first_frame) else None
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
                next_infer_t = 0.0
                while not stop_event.is_set():
                    now_t = time.time()
                    if infer_interval and now_t < next_infer_t:
                        # 限流等待，避免无意义取帧/copy
                        if stop_event.wait(timeout=min(0.05, next_infer_t - now_t)):
                            break
                        continue

                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if stop_event.is_set():
                        break
                    if frame is None:
                        logger.warning("No new RTSP frame for 2s")
                        continue

                    next_infer_t = time.time() + infer_interval

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
                    now = datetime.now()
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
