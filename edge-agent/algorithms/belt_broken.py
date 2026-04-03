import cv2
import numpy as np
from datetime import datetime
import time
from .base import BaseAlgorithm

# 注意：这里如果能引入 ultralytics 最好，如果在边缘端使用不同的推理引擎，
# 这里可以切换为 rknn 或 onnxruntime 调用。这里保留和原先相似的逻辑做演示。

class BeltBrokenAlgorithm(BaseAlgorithm):
    """边缘端 - 皮带表面故障检测（解耦版）"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert):
        logger.info("Starting Belt Broken Algorithm on Edge...")
        
        # 解析配置
        params = config_dict.get('parameters', {})
        confidence = float(params.get('confidence', 0.5))
        alert_threshold = int(params.get('alertThreshold', 5))
        model_path = config_dict.get('model_local_path') # 由 TaskManager 在外层注入真实的本地模型路径

        try:
            from ultralytics import YOLO
            model = YOLO(model_path)
            logger.info(f"Loaded model successfully from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {str(e)}")
            return

        last_alert_time = None

        # 推理循环
        while not stop_event.is_set():
            ret, frame = camera_stream.read()
            if not ret:
                time.sleep(1) # 重试机制
                continue

            try:
                # 使用 YOLO 推理
                results = model(frame, conf=confidence, verbose=False)[0]
                
                # ... (原业务逻辑精简版示例) ...
                if len(results) > 0:
                    defect_detected = False
                    max_conf = 0.0

                    # 假设这里基于 mask 或者 boxes 判断：
                    for box in results.boxes:
                        if box.conf[0] >= confidence:
                            defect_detected = True
                            max_conf = max(max_conf, float(box.conf[0]))

                    # 触发判定与反向回调
                    if defect_detected and self.need_alert_again(last_alert_time, alert_threshold, logger):
                        logger.warning(f"Belt Broken detected! Conf: {max_conf:.2f}")
                        last_alert_time = datetime.now()

                        # 绘制带有告警框的完整图
                        alert_frame = self.draw_and_get_frame(frame, [results])
                        
                        # 把告警抛给上游（由 TaskManager 负责 HTTP POST 给云端并通知 PLC）
                        if on_alert:
                            on_alert("belt_broken", max_conf, alert_frame)

            except Exception as e:
                logger.error(f"Inference error: {str(e)}")
                time.sleep(1)
                
        logger.info("Belt Broken Algorithm stopped.")
