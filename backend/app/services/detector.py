import cv2
from flask import current_app
from app.extensions import socketio, db
from app.models import Alert, Camera, DetectionModel, Task, EdgeNode
import os
from app.models.algorithm import Algorithm
from config import Config
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class DetectorService:
    def __init__(self):
        pass
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
        """启动检测任务（下发给边缘计算节点）"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"success": False, "message": f"Task with id {task_id} not found"}
            
            # 获取算法类型
            algorithm = Algorithm.query.get(task.algorithm_id)
            if not algorithm:
                return {"success": False, "message": "Algorithm not found"}

            # 获取摄像头
            camera = Camera.query.get(task.cameraId)
            if not camera:
                return {"success": False, "message": "Camera not found"}

            # 获取模型
            model = DetectionModel.query.get(task.modelId)
            
            # TODO: 如果还是希望在云端跑（没有edge_node_id的情况），可以保留原逻辑。或者强迫下发。
            if not task.edge_node_id:
                return {"success": False, "message": "此任务未指定边缘计算节点 (edge_node_id 为空)"}

            edge_node = EdgeNode.query.get(task.edge_node_id)
            if not edge_node:
                return {"success": False, "message": f"Edge node {task.edge_node_id} not found"}

            # 生成受保护的模型下载 URL（24小时内有效）
            from app.utils.storage import StorageService
            download_url = StorageService.get_download_url(model.path, expires_in_seconds=86400) if model else ""

            # 组装任务配置负载
            task_payload = {
                "msg_id": f"req_{int(datetime.now().timestamp())}",
                "timestamp": int(datetime.now().timestamp()),
                "task_id": task.id,
                "task_name": task.name,
                "algorithm_type": algorithm.type,
                "camera": {
                    "id": camera.id,
                    "rtsp_url": camera.get_rtsp_url()
                },
                "model": {
                    "id": model.id if model else None,
                    "download_url": download_url,
                    "filename": model.path if model else ""
                },
                "parameters": {
                    "confidence": task.confidence,
                    "alertThreshold": task.alertThreshold,
                    **(task.algorithm_parameters or {})
                }
            }

            from app.services.mqtt_service import mqtt_service
            mqtt_service.publish_task_start(edge_node.mac_address, task_payload)

            task.status = 'syncing'
            task.run_status = 'starting'
            db.session.commit()
            
            logger.info(f"Published task {task_id} to edge node {edge_node.mac_address}")
            return {"success": True, "message": "Task start command sent to edge node"}
            
        except Exception as e:
            logger.error(f"Error starting detection: {str(e)}")
            return {"success": False, "message": str(e)}

    def stop_detection(self, task_id):
        """停止检测任务（下发给边缘计算节点）"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"success": False, "message": "Task not found"}

            task.status = 'stopped'
            db.session.commit()

            if task.edge_node_id:
                edge_node = EdgeNode.query.get(task.edge_node_id)
                if edge_node:
                    from app.services.mqtt_service import mqtt_service
                    mqtt_service.publish_task_stop(edge_node.mac_address, task_id)

            return {"success": True, "message": "Detection stop command sent"}
            
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