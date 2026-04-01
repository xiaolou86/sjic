from .base import EdgeBaseAlgorithm
import cv2
import time
from datetime import datetime
from ultralytics import YOLO
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess

class ObjectDetectionAlgorithm(EdgeBaseAlgorithm):
    """边缘端目标检测算法"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert):
        """处理目标检测视频"""
        try:
            # 解析最新的边侧下发配置
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            task_name = config_dict.get('task_id', 'unknown_task')
            camera = camera_stream
            
            # 在边缘端加载 YOLOv8
            logger.info(f"Loading YOLO model for object_detection from: {model_path}")
            model = YOLO(model_path)
            
            confidence = float(parameters.get('confidence', 0.5))
            algorithm_parameters = parameters.get('algorithm_parameters', {})
            alertThreshold = int(parameters.get('alertThreshold', 10))
            last_alert_time = None
            
            # 获取检测区域
            detection_region = algorithm_parameters.get('detection_region')
            points = None
            frame_size = None
            roi_points = None

            if camera is None:
                logger.error(f"error: camera is None")
                return
            
            if detection_region:
                points = detection_region.get('points', [])
                frame_size = detection_region.get('frame_size', {})

            h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            
            if new_h is None:
                logger.error(f"error: get_letterbox_params return None")
                return

            if points:
                roi_points = transform_points_from_frontend_to_backend(points, frame_size['height'], frame_size['width'], new_h, new_w, top, left)
                if roi_points is None:
                    logger.error(f"error: roi_points is None")
                    return

            while not stop_event.is_set():
                ret, frame = camera.read()
                if not ret:
                    time.sleep(1)
                    continue
                
                # 预处理（Letterbox）
                processed = preprocess(frame, new_h, new_w, top, bottom, left, right)
                if processed is None:
                    continue

                # 推理 - 指定输入类别为人 (classes=[0])
                results = model(processed, imgsz=640, verbose=False, conf=confidence, classes=[0])
                
                # 检查是否有人员在检测区域内
                is_exception = False
                result_confidence = 0
                
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        foot_center = ((x1 + x2) // 2, y2)

                        if roi_points:
                            # 检查点是否在检测区域内
                            if self.is_point_in_roi(foot_center, roi_points, logger):
                                is_exception = True
                                result_confidence = float(box.conf)
                                break

                # 发起告警
                if is_exception and self.need_alert_again(last_alert_time, alertThreshold, logger):
                    last_alert_time = datetime.now()
                    
                    # 生成检测画面截图
                    alert_frame = self.draw_and_get_frame(frame, results)
        
                    # 如果有检测结果，将结果投送给 TaskManager 上传到云端
                    if on_alert:
                        on_alert(
                            alert_type="object_detection", 
                            confidence=result_confidence, 
                            image_frame=alert_frame
                        )
                
                time.sleep(0.01) # 降频节能
                               
        except Exception as e:
            logger.error(f"Error in object detection: {str(e)}", exc_info=True)
            raise
