"""鼠标空闲：依赖边缘侧鼠标活动时间戳文件（有鼠标考场）。"""
from .base import BaseAlgorithm
import os
import time
from datetime import datetime
from utils.rtsp import FramePump, is_valid_frame


class MouseIdleAlgorithm(BaseAlgorithm):
    """
    超过 idle_seconds 无鼠标操作则告警。

    活动来源（按优先级）：
    1. algorithm_parameters.activity_file —— 外部写入 unix 时间戳的文本文件
    2. 环境变量 SJIC_MOUSE_ACTIVITY_FILE
    3. 默认 {models_dir}/mouse_activity_{camera_id}.ts

    桌面侧小助手只需定期写入「最后鼠标活动时间」。
    无活动文件时：任务启动后从当前时刻开始计空闲（便于联调）。
    """

    def _resolve_activity_file(self, config_dict, algo_params):
        if algo_params.get('activity_file'):
            return algo_params['activity_file']
        env_path = os.environ.get('SJIC_MOUSE_ACTIVITY_FILE')
        if env_path:
            return env_path
        models_dir = (config_dict.get('paths') or {}).get('models_dir') or '.'
        cam_id = (config_dict.get('camera') or {}).get('id', '0')
        return os.path.join(models_dir, f'mouse_activity_{cam_id}.ts')

    def _read_last_activity(self, path, fallback_ts):
        try:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    raw = f.read().strip()
                if raw:
                    return float(raw)
        except Exception:
            pass
        return fallback_ts

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        try:
            parameters = config_dict.get('parameters', {})
            algo_params = parameters.get('algorithm_parameters') or {}
            idle_seconds = float(algo_params.get('idle_seconds', 60))
            alert_threshold = int(parameters.get('alertThreshold', 10))
            alert_type = algo_params.get('alert_type') or 'mouse_idle'
            task_name = config_dict.get('task_id', 'unknown_task')
            activity_file = self._resolve_activity_file(config_dict, algo_params)
            logger.info(f"mouse_idle watching activity_file={activity_file} idle_seconds={idle_seconds}")

            started_at = time.time()
            last_alert_time = None

            # 可选挂视频泵：便于告警截图；无流也能跑（仅计时）
            pump = None
            if camera_stream is not None:
                rtsp_url = config_dict.get('camera', {}).get('rtsp_url')
                pump = FramePump(camera_stream, stop_event, rtsp_url, logger)
                pump.start()

            try:
                last_seq = 0
                while not stop_event.is_set():
                    last_act = self._read_last_activity(activity_file, started_at)
                    idle_for = time.time() - last_act
                    now = datetime.now()

                    frame = None
                    if pump is not None:
                        frame, last_seq = pump.get_latest(last_seq=last_seq, wait_sec=0.5)

                    if idle_for < idle_seconds:
                        time.sleep(0.5)
                        continue
                    if last_alert_time and (now - last_alert_time).total_seconds() < alert_threshold:
                        time.sleep(0.5)
                        continue

                    message = f"超过 {idle_seconds:.0f}s 无鼠标操作（已空闲 {idle_for:.0f}s）"
                    alert_frame = frame if (frame is not None and is_valid_frame(frame)) else None
                    if alert_frame is not None:
                        alert_frame = self.draw_alert_overlay(alert_frame, caption=message)
                    logger.info(f"Triggering {alert_type} for {task_name}")
                    if on_alert:
                        on_alert(
                            alert_type=alert_type,
                            confidence=1.0,
                            image_frame=alert_frame,
                            message=message,
                        )
                    last_alert_time = now
                    time.sleep(1.0)
            finally:
                if pump is not None:
                    pump.release()
        except Exception as e:
            logger.error(f"Error in mouse_idle: {str(e)}", exc_info=True)
            raise
