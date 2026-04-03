import cv2
from flask import current_app
from app.extensions import socketio, db
from app.models import Alert, Camera, DetectionModel, Task, EdgeNode
import os
from app.models.algorithm import Algorithm
from config import Config
import requests
from datetime import datetime

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
            
            current_app.logger.info(f"Published task {task_id} to edge node {edge_node.mac_address}")
            db.session.commit()
            
            return {"success": True, "message": "Task start command sent to edge node"}
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"Error starting detection: {str(e)}\n{traceback.format_exc()}")
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
            current_app.logger.error(f"Error stopping detection: {str(e)}")
            return {"success": False, "message": str(e)}
        

    # Legacy `_detect_loop`, `_send_alert_to_external_api` functions have been completely migrated to Edge-Agent task_manager 
    # and backend alert_routes callbacks.
