from .base import BaseAlgorithm
from .rules import build_rules
import cv2
import time
from datetime import datetime
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess
from utils.rtsp import FramePump, is_valid_frame


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
            pump = FramePump(camera, stop_event, rtsp_url, logger)
            pump.start()
            try:
                runtime.load(model_path)

                confidence = float(parameters.get('confidence', 0.5))
                algorithm_parameters = parameters.get('algorithm_parameters') or {}
                alert_threshold = int(parameters.get('alertThreshold', 10))

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
                while not stop_event.is_set():
                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if frame is None:
                        logger.warning("No new RTSP frame for 2s")
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
                    now = datetime.now()
                    frame_idx += 1

                    if frame_idx == 1 or time.time() - last_log >= 5:
                        logger.info(
                            f"Frame #{frame_idx} infer={infer_ms:.0f}ms boxes={len(boxes)} rules={len(rules)}"
                        )
                        last_log = time.time()

                    for rule in rules:
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
                        )
            finally:
                pump.release()

        except Exception as e:
            logger.error(f"Error in object detection: {str(e)}", exc_info=True)
            raise
