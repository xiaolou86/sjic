from .base import BaseAlgorithm
from app.models import Algorithm, Alert
from flask import current_app
from app.extensions import db
import cv2
import torch
import time
from datetime import datetime
from ultralytics.utils.files import increment_path
from pathlib import Path
from app.utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess

class ObjectDetectionAlgorithm(BaseAlgorithm):
    """目标检测算法"""
    __tablename__ = 'algorithms'
    __mapper_args__ = {
        'polymorphic_identity': 'object_detection'
    }

    @classmethod
    def register(cls):
        type_name = cls.__mapper_args__['polymorphic_identity']
        algorithm = Algorithm.query.filter_by(type=type_name).first()
        if not algorithm:
            algorithm = cls(
                name='目标检测',
                type=type_name,
                description='目标检测，支持人员闯入检测，可指定检测区域'
            )
            db.session.add(algorithm)
            db.session.commit()

    def process(self, camera, parameters):
        """目标检测算法"""
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
            
            # 获取检测区域
            detection_region = algorithm_parameters.get('detection_region')
            points = None
            frame_size = None
            roi_points = None

            if camera is None:
                current_app.logger.error(f"error: camera is None")
                return
            
            if detection_region:
                points = detection_region.get('points', [])
                frame_size = detection_region.get('frame_size', {})

            fps, fourcc = int(camera.get(5)), cv2.VideoWriter_fourcc(*"mp4v")
            h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            current_app.logger.info(f"new_h: {new_h}, new_w: {new_w}, top: {top}, bottom: {bottom}, left: {left}, right: {right}")
            if new_h is None:
                current_app.logger.error(f"error: get_letterbox_params return None")
                return

            if points:
                roi_points = transform_points_from_frontend_to_backend(points, frame_size['height'], frame_size['width'], new_h, new_w, top, left)
                current_app.logger.debug(f"points: {points}")
                current_app.logger.debug(f"roi_points: {roi_points}")
                if roi_points is None:
                    current_app.logger.error(f"error: roi_points is None")
                    return

            # 目标帧率
            target_fps = 20
            frame_delay = 1.0 / target_fps  # 每帧的延迟时间

            # 初始化计数器和时间戳
            frame_count = 0
            start_time = time.time()

            batch_size = 8
            batch = []

            # for test
            on_alert(None, {
                'confidence': 0.5,
                'image_url': 'test.jpg',
            })
            current_app.logger.debug(f"class    person_index: {model.names}")

            while True:
                if stop_event and stop_event.is_set():
                    current_app.logger.info(f"Stop event set for task {task_name}")
                    break

                ret, frame = camera.read()
                if not ret:
                    time.sleep(1)
                    continue
                
                # 预处理（Letterbox）
                processed = preprocess(frame, new_h, new_w, top, bottom, left, right)
                if processed is None:
                    continue

                # 推理
                results = model(processed, imgsz=640, verbose=False, conf=confidence, classes=[0])  # 指定输入尺寸
                print("results.lenght:=================================", len(results))
                
                # 检查是否有人员在检测区域内
                is_exception = False
                result_confidence = 0
                
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        # 只处理类别为0(person)的检测结果
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        current_app.logger.debug(f"Detection box: {box.xyxy[0]}")
                        # box_center = ((x1 + x2) // 2, (y1 + y2) // 2)
                        foot_center = ((x1 + x2) // 2, y2)
                        current_app.logger.debug(f"Box foot center: {foot_center}")

                        if roi_points:
                            # 检查点是否在检测区域内
                            if self.is_point_in_roi(foot_center, roi_points):
                                is_exception = True
                                result_confidence = float(box.conf)
                                current_app.logger.debug(f"Point in ROI: True.")
                                current_app.logger.debug(f"result_confidence: {result_confidence}")
                                break

                #cv2.imshow('frame', results[0].plot())
                #cv2.waitKey(0)

                if is_exception and self.need_alert_again(last_alert_time, alertThreshold):
                    current_app.logger.debug(f"need_alert_again: True")
                    last_alert_time = datetime.now()
                    # TODO: 保存检测结果
                    save_filename = self.save_detection_image(frame, results, task_name)
                    current_app.logger.debug(f"save_filename: {save_filename}")
        
                    # 如果有检测结果，调用告警处理回调
                    if on_alert:
                        current_app.logger.debug(f"Calling on_alert")
                        on_alert(frame, {
                            'confidence': result_confidence,
                            'image_url': save_filename,
                        })
                               
        except Exception as e:
            current_app.logger.error(f"Error in object detection: {str(e)}")
            raise
