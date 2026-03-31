from .base import BaseAlgorithm
from flask import current_app
from app.extensions import db
from app.models import Algorithm
import cv2
import numpy as np
from datetime import datetime
from shapely.geometry import LineString, Polygon
import time
from app.utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess, preprocess_return_numpy
import torch


class BeltDeviationDetection(BaseAlgorithm):
    """皮带跑偏检测算法"""
    __tablename__ = 'algorithms'
    __mapper_args__ = {
        'polymorphic_identity': 'belt_deviation_detecion'
    }
    
    @classmethod
    def register(cls):
        type_name = cls.__mapper_args__['polymorphic_identity']
        print(type_name)
        algorithm = Algorithm.query.filter_by(type=type_name).first()
        print(algorithm)
        if algorithm:
            algorithm.name = '皮带跑偏检测/堆煤检测'
            algorithm.description = '皮带跑偏检测算法/堆煤检测算法，当超过设置的边界线时推送告警。'

        else:
            algorithm = cls(
                name='皮带跑偏检测/堆煤检测',
                type=type_name,
                description='皮带跑偏检测算法/堆煤检测算法，当超过设置的边界线时推送告警。'
            )
            db.session.add(algorithm)
        db.session.commit()
    
    def process(self, camera, parameters):
        """处理图像"""
        try:
            model = parameters.get('model')
            task_name = parameters.get('task_name')
            confidence = parameters.get('confidence', 0.5)
            algorithm_parameters = parameters.get('algorithm_parameters', {})
            on_alert = parameters.get('on_alert')  # 获取告警处理回调
            alertThreshold = parameters.get('alertThreshold', 1800)
            last_alert_time = None
            camera_id = parameters.get('camera_id')
            stop_event = parameters.get('stop_event')

            if camera is None:
                current_app.logger.error(f"error: camera is None")
                return
            
            # 获取标定数据
            calibration = algorithm_parameters.get('calibration', {})
            if not calibration:
                current_app.logger.error("未找到标定数据，无法进行皮带跑偏检测")
                return
                
            boundary_lines = calibration.get('boundary_lines', [])  # 边界线坐标
            if len(boundary_lines) != 2:
                current_app.logger.error(f"边界线数量错误，期望2条，实际{len(boundary_lines)}条")
                return
                
            frame_size = calibration.get('frame_size', {})         # 前端显示的帧尺寸
            boundary_distance = calibration.get('boundary_distance', 0)  # 边界线间实际距离(cm)
            deviation_threshold = calibration.get('deviation_threshold', 0)  # 跑偏报警阈值(cm)
            
            current_app.logger.info(f"皮带跑偏检测参数: 边界线距离={boundary_distance}cm, 跑偏阈值={deviation_threshold}cm")
            
            h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            
            # 将前端坐标转换为实际图像坐标
            actual_lines = []
            points = []
            line_points = []
            for line in boundary_lines:
                for point in line:
                    points.append(point)
            if points:
                line_points = transform_points_from_frontend_to_backend(points, frame_size['height'], frame_size['width'], new_h, new_w, top, left)
                current_app.logger.debug(f"points: {points}")
                current_app.logger.debug(f"roi_points: {line_points}")
                if line_points is None:
                    current_app.logger.error(f"error: line_points is None")
                    return
            
            actual_line = []
            for p in line_points:
                actual_line.append(p)
                if len(actual_line) == 2:
                    actual_lines.append(actual_line)
                    actual_line = []
            if len(actual_lines) != 2:
                current_app.logger.error("actual_lines: need to have 2 lines!")

            while not stop_event.is_set():
                # 读取一帧
                ret, frame = camera.read()
                if not ret:
                    current_app.logger.warning("无法读取视频帧")
                    time.sleep(1)
                    continue

                # 预处理（Letterbox）
                processed = preprocess(frame, new_h, new_w, top, bottom, left, right)               
                                
                # 使用模型检测皮带
                # TODO
                results = model(processed, imgsz=640, verbose=False, conf=confidence)
                #results = model(processed, imgsz=640, verbose=False, conf=confidence, classes=[0])
                
                # 检查是否有分割结果
                if len(results) > 0 and hasattr(results[0], 'masks') and results[0].masks is not None:
                    # 获取皮带的分割掩码
                    masks = results[0].masks
                    if len(masks) > 0:
                        # 获取第一个掩码（假设只有一个皮带）
                        belt_mask = masks[0].data.cpu().numpy()[0]  # 形状为 (H, W)
                        
                        # 将掩码转换为二值图像
                        belt_mask = (belt_mask > 0.5).astype(np.uint8) * 255
                        
                        # 找到皮带的轮廓
                        contours, _ = cv2.findContours(belt_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        
                        if contours:
                            # 获取最大的轮廓（假设是皮带）
                            belt_contour = max(contours, key=cv2.contourArea)
                            
                            # 创建皮带的多边形
                            belt_polygon = Polygon(belt_contour.reshape(-1, 2))
                            
                            # 检查皮带是否与边界线相交
                            is_deviation = False
                            for line in actual_lines:
                                boundary_line = LineString(line)
                                if belt_polygon.intersects(boundary_line):
                                    is_deviation = True
                                    break
                            
                            # 如果检测到跑偏并且需要告警
                            if is_deviation and self.need_alert_again(last_alert_time, alertThreshold):
                                current_app.logger.warning("检测到皮带跑偏！")
                                last_alert_time = datetime.now()

                                # 创建一个副本用于可视化
                                processed_numpy = preprocess_return_numpy(frame, new_h, new_w, top, bottom, left, right)               
                                vis_frame = processed_numpy.copy()
                                
                                # 绘制边界线
                                for line in actual_lines:
                                    cv2.line(vis_frame, line[0], line[1], (0, 0, 255), 2)
                                    current_app.logger.debug(f"line: {line}")
                                
                                # 在可视化图像上绘制皮带轮廓
                                cv2.drawContours(vis_frame, [belt_contour], -1, (0, 255, 0), 2)
                                                                
                                # 获取YOLO的可视化结果
                                plotted_img = results[0].plot()
                                if isinstance(plotted_img, torch.Tensor):
                                    plotted_img = plotted_img.cpu().numpy()
                                
                                # 在YOLO结果上绘制边界线和轮廓
                                for line in actual_lines:
                                    cv2.line(plotted_img, line[0], line[1], (0, 0, 255), 2)
                                
                                cv2.drawContours(plotted_img, [belt_contour], -1, (0, 255, 0), 2)
                                
                                # 保存带有额外信息的图像
                                save_filename = self.save_detection_image(plotted_img, None, task_name, use_frame=True)
                            
                                # 调用告警回调
                                if on_alert:
                                    on_alert(vis_frame, {
                                        'confidence': 1.0,  # 置信度设为1.0
                                        'image_url': save_filename,
                                        'alert_type': 'belt_deviation_detecion',
                                        'message': '皮带跑偏告警'
                                    })
                
                # 检查是否需要停止
                if stop_event.is_set():
                    break
                
                # 控制处理速度
                time.sleep(0.01)
                
        except Exception as e:
            current_app.logger.error(f"皮带跑偏检测错误: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            raise
