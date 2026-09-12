"""画面健康：黑屏 / 大面积遮挡（无需检测模型）。"""
from .base import BaseAlgorithm
import cv2
import time
from datetime import datetime
from utils.rtsp import FramePump, is_valid_frame


class CameraHealthAlgorithm(BaseAlgorithm):
    """监控画面突然变黑或被挡住。"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        try:
            parameters = config_dict.get('parameters', {})
            algo_params = parameters.get('algorithm_parameters') or {}
            alert_threshold = int(parameters.get('alertThreshold', 10))
            black_ratio = float(algo_params.get('black_ratio', 0.85))
            variance_threshold = float(algo_params.get('variance_threshold', 12.0))
            hold_seconds = float(algo_params.get('seconds', 3))
            alert_type = algo_params.get('alert_type') or 'camera_blocked'
            task_name = config_dict.get('task_id', 'unknown_task')

            if camera_stream is None:
                logger.error("error: camera is None")
                return

            rtsp_url = config_dict.get('camera', {}).get('rtsp_url')
            pump = FramePump(camera_stream, stop_event, rtsp_url, logger)
            pump.start()
            try:
                last_seq = 0
                bad_since = None
                last_alert_time = None
                while not stop_event.is_set():
                    frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=2.0)
                    if stop_event.is_set():
                        break
                    if frame is None or not is_valid_frame(frame):
                        logger.warning("No valid frame for camera health check")
                        continue

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    mean_val = float(gray.mean())
                    var_val = float(gray.var())
                    # 近全黑，或整体方差极低（大面积遮挡/贴布）
                    is_bad = (mean_val < (1.0 - black_ratio) * 255.0) or (var_val < variance_threshold)

                    now = datetime.now()
                    if not is_bad:
                        bad_since = None
                        continue
                    if bad_since is None:
                        bad_since = now
                        continue
                    elapsed = (now - bad_since).total_seconds()
                    if elapsed < hold_seconds:
                        continue
                    if last_alert_time and (now - last_alert_time).total_seconds() < alert_threshold:
                        continue

                    message = (
                        f"摄像头画面异常：mean={mean_val:.1f} var={var_val:.1f} "
                        f"持续 {elapsed:.1f}s"
                    )
                    caption = message
                    alert_frame = self.draw_alert_overlay(frame, caption=caption)
                    logger.info(f"Triggering {alert_type} for {task_name}")
                    if on_alert:
                        on_alert(
                            alert_type=alert_type,
                            confidence=1.0,
                            image_frame=alert_frame,
                            message=message,
                        )
                    last_alert_time = now
                    bad_since = now
                    time.sleep(0.05)
            finally:
                pump.release()
        except Exception as e:
            logger.error(f"Error in camera_health: {str(e)}", exc_info=True)
            raise
