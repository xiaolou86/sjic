from .base import EdgeBaseAlgorithm
import cv2
import numpy as np
from datetime import datetime
from shapely.geometry import LineString, Polygon
import time
from ultralytics import YOLO
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess, preprocess_return_numpy
import torch

class BeltDeviationDetection(EdgeBaseAlgorithm):
    """边缘端：皮带跑偏检测算法"""
    
    def process(self, camera_stream, config_dict, logger, stop_event, on_alert):
        """处理视频流"""
        try:
            # 获取基本参数
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            task_name = config_dict.get('task_id', 'unknown_task')
            camera = camera_stream
            
            logger.info(f"Loading YOLO (Segmentation) model from: {model_path}")
            model = YOLO(model_path)
            
            confidence = float(parameters.get('confidence', 0.5))
            algorithm_parameters = parameters.get('algorithm_parameters', {})
            alertThreshold = int(parameters.get('alertThreshold', 1800))
            last_alert_time = None

            if camera is None:
                logger.error(f"error: camera is None")
                return
            
            # 获取跑偏标定数据
            calibration = algorithm_parameters.get('calibration', {})
            if not calibration:
                logger.error("未找到跑偏标定数据")
                return
                
            boundary_lines = calibration.get('boundary_lines', []) 
            if len(boundary_lines) != 2:
                logger.error(f"边界线数量错误，期望2条，实际{len(boundary_lines)}条")
                return
                
            frame_size = calibration.get('frame_size', {})
            deviation_threshold = float(calibration.get('deviation_threshold', 0))
            
            h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            
            # 前端坐标转换
            points = []
            for line in boundary_lines:
                for point in line:
                    points.append(point)
            
            line_points = transform_points_from_frontend_to_backend(points, frame_size['height'], frame_size['width'], new_h, new_w, top, left)
            
            if not line_points:
                logger.error("坐标转换失败")
                return

            actual_lines = [
                [line_points[0], line_points[1]],
                [line_points[2], line_points[3]]
            ]

            while not stop_event.is_set():
                ret, frame = camera.read()
                if not ret:
                    time.sleep(1)
                    continue

                processed = preprocess(frame, new_h, new_w, top, bottom, left, right)               
                                
                # 使用边缘模型执行推理
                results = model(processed, imgsz=640, verbose=False, conf=confidence)
                
                # 分割掩码分析
                if len(results) > 0 and hasattr(results[0], 'masks') and results[0].masks is not None:
                    masks = results[0].masks
                    if len(masks) > 0:
                        belt_mask = masks[0].data.cpu().numpy()[0]
                        belt_mask = (belt_mask > 0.5).astype(np.uint8) * 255
                        
                        contours, _ = cv2.findContours(belt_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        
                        if contours:
                            belt_contour = max(contours, key=cv2.contourArea)
                            belt_polygon = Polygon(belt_contour.reshape(-1, 2))
                            
                            # 判断跑到边界外的交点
                            is_deviation = False
                            for line in actual_lines:
                                boundary_line = LineString(line)
                                if belt_polygon.intersects(boundary_line):
                                    is_deviation = True
                                    break
                            
                            # 如果跑偏
                            if is_deviation and self.need_alert_again(last_alert_time, alertThreshold, logger):
                                logger.warning("!!! 检测到煤矿皮带跑偏 !!!")
                                last_alert_time = datetime.now()

                                processed_numpy = preprocess_return_numpy(frame, new_h, new_w, top, bottom, left, right)               
                                vis_frame = processed_numpy.copy()
                                
                                # 画图
                                for line in actual_lines:
                                    cv2.line(vis_frame, line[0], line[1], (0, 0, 255), 2)
                                
                                cv2.drawContours(vis_frame, [belt_contour], -1, (0, 255, 0), 2)
                                
                                # 触发告警抛到设备管理器
                                if on_alert:
                                    on_alert(
                                        alert_type="belt_deviation_detection",
                                        confidence=1.0,  # 图像分割交点确信度
                                        image_frame=vis_frame
                                    )
                
                time.sleep(0.01)

        except Exception as e:
            logger.error(f"皮带跑偏检测致命错误: {str(e)}", exc_info=True)
            raise
