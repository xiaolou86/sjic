import cv2
import numpy as np
from datetime import datetime
import time
from .base import BaseAlgorithm


class BeltBrokenAlgorithm(BaseAlgorithm):
    """边缘端 - 皮带表面故障检测（解耦版）"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        logger.info("Starting Belt Broken Algorithm on Edge...")
        
        # 解析配置
        params = config_dict.get('parameters', {})
        confidence = float(params.get('confidence', 0.5))
        alert_threshold = int(params.get('alertThreshold', 5))
        model_path = config_dict.get('model_local_path')

        # 通过 Runtime 抽象加载模型
        try:
            runtime.load(model_path)
            logger.info(f"Loaded model successfully via runtime from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            return

        last_alert_time = None

        # 推理循环
        while not stop_event.is_set():
            ret, frame = camera_stream.read()
            if not ret:
                time.sleep(1) # 重试机制
                continue

            try:
                # 通过 Runtime 推理
                result = runtime.infer(frame, conf=confidence)
                
                if result.count > 0:
                    defect_detected = False
                    max_conf = 0.0

                    for box in result.boxes:
                        if box.confidence >= confidence:
                            defect_detected = True
                            max_conf = max(max_conf, box.confidence)

                    # 触发判定与反向回调
                    if defect_detected and self.need_alert_again(last_alert_time, alert_threshold, logger):
                        logger.warning(f"Belt Broken detected! Conf: {max_conf:.2f}")
                        last_alert_time = datetime.now()

                        # 绘制带有告警框的完整图
                        alert_frame = self.draw_and_get_frame(frame, result)
                        
                        # 把告警抛给上游（由 TaskManager 负责 HTTP POST 给云端并通知 PLC）
                        if on_alert:
                            on_alert("belt_broken", max_conf, alert_frame)

            except Exception as e:
                logger.error(f"Inference error: {str(e)}")
                time.sleep(1)
                
        logger.info("Belt Broken Algorithm stopped.")
