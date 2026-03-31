import cv2
import numpy as np
from ultralytics import YOLO
from flask import current_app
from app.extensions import socketio, db
import torch
from app.models import Alert, Camera, DetectionModel, Task
import os
from app.models.algorithm import Algorithm
from config import Config
import logging
import requests
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)

class DetectorService:
    def __init__(self):
        self.running = False
        self.camera = None
        self.model = None
        self.task = None
        self.active_detectors = {}  # 存储每个任务的检测状态
        self.detection_threads = {}  # 存储每个任务的线程对象
        self.stop_events = {}  # 存储每个任务的停止事件

    def load_camera(self, camera_id):
        """加载摄像头"""
        camera = Camera.query.get(camera_id)
        if not camera:
            raise ValueError(f"Camera with id {camera_id} not found")
        return camera
        
    def load_model(self, model_id):
        """加载YOLO模型"""
        try:
            model = DetectionModel.query.get(model_id)
            if not model:
                raise ValueError(f"Model with id {model_id} not found")

            # 使用绝对路径
            model_path = os.path.join(Config.MODEL_FOLDER, model.path)
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")

            return YOLO(model_path)
        except Exception as e:
            raise Exception(f"模型加载失败: {str(e)}")
            
    def create_alert(self, camera_id, alert_type, confidence, image_url):
        """创建告警记录"""
        alert = Alert(
            camera_id=camera_id,
            alert_type=alert_type,
            confidence=confidence,
            image_url=image_url
        )
        
        db.session.add(alert)
        db.session.commit()
        
        # 发送实时告警
        socketio.emit('new_alert', alert.to_dict())
        
        return alert

    def start_detection(self, task_id):
        """启动检测任务"""
        try:
            # 获取任务信息
            task = Task.query.get(task_id)
            if not task:
                return {"success": False, "message": f"Task with id {task_id} not found"}
            
            # 检查任务是否已经在运行
            if task_id in self.active_detectors:
                logger.info(f"Task {task_id} is already running")
                task.status = 'running'
                db.session.commit()
                return {"success": True, "message": "Task is already running"}
            
            # 加载摄像头
            camera = self.load_camera(task.cameraId)
            rtsp_url = camera.get_rtsp_url()
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                return {"success": False, "message": f"Failed to open camera with rtsp url: {rtsp_url}"}
            
            # 加载模型
            model = self.load_model(task.modelId)
                        
            # 更新任务状态
            task.status = 'running'
            db.session.commit()
            
            # 创建停止事件
            stop_event = threading.Event()
            self.stop_events[task_id] = stop_event
            
            # 标记任务为运行状态
            self.active_detectors[task_id] = {
                'task_id': task_id,
                'camera': cap,
                'model': model,
                'rtsp_url': rtsp_url
            }
            
            # 保存 app 引用供线程使用
            app = current_app._get_current_object()
            
            # 创建并启动检测线程
            detection_thread = threading.Thread(
                target=self._detect_loop,
                args=(task_id, stop_event, app),
                daemon=True
            )
            self.detection_threads[task_id] = detection_thread
            detection_thread.start()
            
            logger.info(f"Started detection for task {task_id}")
            return {"success": True, "message": "Detection started"}
            
        except Exception as e:
            logger.error(f"Error starting detection: {str(e)}")
            return {"success": False, "message": str(e)}

    def stop_detection(self, task_id):
        """停止检测任务"""
        try:
            # 更新任务状态
            task = Task.query.get(task_id)
            if task:
                task.status = 'stopped'
                db.session.commit()

            # 检查任务是否在运行
            if task_id not in self.active_detectors:
                logger.info(f"Task {task_id} is not running")
                return {"success": True, "message": "Task is not running"}
            
            # 设置停止事件
            if task_id in self.stop_events:
                self.stop_events[task_id].set()
                logger.info(f"Stop event set for task {task_id}")
            
            # 等待线程结束（可选，设置超时）
            if task_id in self.detection_threads:
                thread = self.detection_threads[task_id]
                if thread.is_alive():
                    # 等待线程结束，最多等待3秒
                    thread.join(timeout=3)
                    if thread.is_alive():
                        logger.warning(f"Thread for task {task_id} did not terminate within timeout")
                
                # 从字典中移除线程引用
                del self.detection_threads[task_id]
            
            # 清理停止事件
            if task_id in self.stop_events:
                del self.stop_events[task_id]

            if self.active_detectors[task_id]['camera'] and self.active_detectors[task_id]['camera'].isOpened():
                self.active_detectors[task_id]['camera'].release()
            del self.active_detectors[task_id]
            
            logger.info(f"Stopped detection for task {task_id}")
            return {"success": True, "message": "Detection stopped"}
            
        except Exception as e:
            logger.error(f"Error stopping detection: {str(e)}")
            return {"success": False, "message": str(e)}
        

    def _detect_loop(self, task_id, stop_event, app):
        """检测循环"""
        with app.app_context():
            try:
                detector = self.active_detectors[task_id]
                task = Task.query.get(detector['task_id'])
                algorithm = Algorithm.get_algorithm_by_id(task.algorithm_id)
                
                def handle_alert(frame, alert_data):
                    try:
                        # 创建告警记录
                        alert = Alert(
                            camera_id=task.cameraId,
                            alert_type=algorithm.type,
                            confidence=alert_data.get('confidence', 0),
                            image_url=alert_data.get('image_url', ''),
                            timestamp=datetime.now()
                        )
                        db.session.add(alert)
                        db.session.commit()
                        
                        # 调用第三方 REST API 发送告警
                        self._send_alert_to_external_api(alert.to_dict())
                        
                    except Exception as e:
                        logger.error(f"Error handling alert: {str(e)}")

                # 启动算法处理
                algorithm.process(detector['camera'], {
                    'model': detector['model'],
                    'camera_id': task.cameraId,
                    'task_name': task.name,
                    'confidence': task.confidence,
                    'alertThreshold': task.alertThreshold,
                    'algorithm_parameters': task.algorithm_parameters,
                    'on_alert': handle_alert,  # 传递告警处理回调
                    'stop_event': stop_event
                })

            except Exception as e:
                logger.error(f"Error in detection loop: {str(e)}")
                self.stop_detection(task_id)

    def _send_alert_to_external_api(self, alert_data):
        """发送告警到外部 API"""
        # todo
        logger.info(f"_send_alert_to_external_api: {alert_data}")
        return
    
        try:
            # 配置外部 API 的 URL
            api_url = current_app.config.get('EXTERNAL_ALERT_API_URL')
            if not api_url:
                logger.warning("External alert API URL not configured")
                return

            # 发送 POST 请求
            response = requests.post(
                api_url,
                json=alert_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f"Bearer {current_app.config.get('EXTERNAL_API_TOKEN')}"
                }
            )
            
            if not response.ok:
                logger.error(f"Failed to send alert to external API: {response.text}")
                
        except Exception as e:
            logger.error(f"Error sending alert to external API: {str(e)}")

    def _save_detection_image(self, frame, results):
        """保存检测图片"""
        try:
            # 创建保存目录
            save_dir = current_app.config['ALERT_FOLDER']
            os.makedirs(save_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            filename = f'detection_{timestamp}.jpg'
            filepath = os.path.join(save_dir, filename)
            
            # 保存图像
            cv2.imwrite(filepath, frame)
            
            return filename
            
        except Exception as e:
            logger.error(f"Error saving detection image: {str(e)}")
            return None