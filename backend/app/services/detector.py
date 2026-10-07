import cv2
from flask import current_app
from app.extensions import socketio, db
from app.models import Alert, Camera, DetectionModel, Task, EdgeNode
import os
from app.models.algorithm import Algorithm
from config import Config
import requests
from datetime import datetime
from app.models.camera import normalize_mount_position
from app.services.license_service import license_service

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
        camera = Camera.query.get(camera_id)
        alert = Alert(
            camera_id=camera_id,
            camera_name=camera.name if camera else None,
            alert_type=alert_type,
            confidence=confidence,
            image_url=image_url,
            review_status='pending',
        )

        db.session.add(alert)
        db.session.commit()

        from app.utils.algorithm_catalog import label_for_alert_type
        payload = alert.to_dict()
        payload['alert_type_label'] = label_for_alert_type(alert.alert_type)
        socketio.emit('new_alert', payload)

        return alert

    def start_detection(self, task_id):
        """启动检测任务（下发给边缘计算节点）"""
        try:
            ok, reason = license_service.ensure_valid()
            if not ok:
                return {"success": False, "message": f"License invalid: {reason}"}

            task = Task.query.get(task_id)
            if not task:
                return {"success": False, "message": f"Task with id {task_id} not found"}

            if task.is_exam_pipeline():
                return self._start_exam_pipeline(task)
            
            # 获取算法类型
            algorithm = Algorithm.query.get(task.algorithm_id)
            if not algorithm:
                return {"success": False, "message": "Algorithm not found"}

            publish_meta = (algorithm.parameter_schema or {}).get('publish_meta', {})
            if not bool(publish_meta.get('published', False)):
                return {"success": False, "message": "Algorithm is not published"}

            allowed, deny_reason = license_service.is_algorithm_allowed(algorithm.type)
            if not allowed:
                return {"success": False, "message": f"Algorithm not allowed by license: {deny_reason}"}

            # 获取摄像头
            camera = Camera.query.get(task.cameraId)
            if not camera:
                return {"success": False, "message": "Camera not found"}

            from app.utils.algorithm_catalog import engine_needs_model

            engine = algorithm.resolved_engine()
            needs_model = engine_needs_model(engine)

            model = None
            download_url = ""
            if needs_model:
                if not algorithm.model_id:
                    return {"success": False, "message": f"Algorithm {algorithm.name} is not bound to a model"}
                model = DetectionModel.query.get(algorithm.model_id)
                if not model:
                    return {"success": False, "message": "Bound model not found"}
                from app.utils.storage import StorageService
                download_url = StorageService.get_download_url(model.path, expires_in_seconds=86400)

            if not task.edge_node_id:
                return {"success": False, "message": "此任务未指定边缘计算节点 (edge_node_id 为空)"}

            edge_node = EdgeNode.query.get(task.edge_node_id)
            if not edge_node:
                return {"success": False, "message": f"Edge node {task.edge_node_id} not found"}

            # algorithm_type = 边缘引擎；algorithm_code = 产品算法标识
            task_payload = {
                "msg_id": f"req_{int(datetime.now().timestamp())}",
                "timestamp": int(datetime.now().timestamp()),
                "task_id": task.id,
                "task_name": task.name,
                "algorithm_type": engine,
                "algorithm_code": algorithm.type,
                "algorithm_id": algorithm.id,
                "camera": {
                    "id": camera.id,
                    "rtsp_url": camera.get_rtsp_url(),
                    "mount_position": normalize_mount_position(camera.mount_position),
                },
                "model": {
                    "id": model.id if model else None,
                    "download_url": download_url,
                    "filename": model.path if model else "",
                    "required": needs_model,
                },
                "parameters": {
                    "confidence": task.confidence,
                    "alertThreshold": task.alertThreshold,
                    "algorithm_parameters": task.algorithm_parameters,
                    # 服务商在算法实例上配置的推理帧率（客户任务不可改）
                    "inferFps": algorithm.resolved_infer_fps(),
                    # 任务级每日运行时段；场景级 schedule_* 优先
                    "schedule_start": task.schedule_start,
                    "schedule_end": task.schedule_end,
                }
            }

            from app.services.mqtt_service import mqtt_service
            mqtt_service.publish_task_start(edge_node.mac_address, task_payload)

            task.status = 'syncing'
            task.run_status = 'starting'
            # 手动/自动启动后，允许调度器继续按时段管理
            if task.has_schedule():
                task.schedule_paused = False
            
            current_app.logger.info(f"Published task {task_id} to edge node {edge_node.mac_address}")
            db.session.commit()
            
            return {"success": True, "message": "Task start command sent to edge node"}
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"Error starting detection: {str(e)}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _model_payload(self, algorithm):
        if not algorithm or not algorithm.model_id:
            return None
        model = DetectionModel.query.get(algorithm.model_id)
        if not model:
            return None
        from app.utils.storage import StorageService
        return {
            "id": model.id,
            "download_url": StorageService.get_download_url(model.path, expires_in_seconds=86400),
            "filename": model.path,
            "required": True,
            "algorithm_id": algorithm.id,
            "infer_fps": algorithm.resolved_infer_fps(),
        }

    def _start_exam_pipeline(self, task):
        """同一路视频。按启用场景决定下发检测模型、姿态模型或两者。"""
        from app.utils.exam_task import scene_needs

        try:
            needs = scene_needs(task.algorithm_parameters)
            if not needs['need_od'] and not needs['need_pose']:
                return {"success": False, "message": "没有启用的场景"}

            od_algo = Algorithm.query.get(task.od_algorithm_id) if needs['need_od'] else None
            pose_algo = Algorithm.query.get(task.pose_algorithm_id) if needs['need_pose'] else None
            if needs['need_od'] and not od_algo:
                return {"success": False, "message": "目标检测算法未绑定"}
            if needs['need_pose'] and not pose_algo:
                return {"success": False, "message": "姿态算法未绑定"}

            for algorithm in (od_algo, pose_algo):
                if not algorithm:
                    continue
                publish_meta = (algorithm.parameter_schema or {}).get('publish_meta', {})
                if not bool(publish_meta.get('published', False)):
                    return {"success": False, "message": f"Algorithm {algorithm.name} is not published"}
                allowed, deny_reason = license_service.is_algorithm_allowed(algorithm.type)
                if not allowed:
                    return {"success": False, "message": f"Algorithm not allowed by license: {deny_reason}"}
                if not algorithm.model_id:
                    return {"success": False, "message": f"Algorithm {algorithm.name} is not bound to a model"}

            camera = Camera.query.get(task.cameraId)
            if not camera:
                return {"success": False, "message": "Camera not found"}
            if not task.edge_node_id:
                return {"success": False, "message": "此任务未指定边缘计算节点 (edge_node_id 为空)"}
            edge_node = EdgeNode.query.get(task.edge_node_id)
            if not edge_node:
                return {"success": False, "message": f"Edge node {task.edge_node_id} not found"}

            models = {}
            fps_values = []
            if od_algo:
                payload = self._model_payload(od_algo)
                if not payload:
                    return {"success": False, "message": "Bound detection model not found"}
                models['object_detection'] = payload
                fps_values.append(payload['infer_fps'])
            if pose_algo:
                payload = self._model_payload(pose_algo)
                if not payload:
                    return {"success": False, "message": "Bound pose model not found"}
                models['pose_behavior'] = payload
                fps_values.append(payload['infer_fps'])

            task_payload = {
                "msg_id": f"req_{int(datetime.now().timestamp())}",
                "timestamp": int(datetime.now().timestamp()),
                "task_id": task.id,
                "task_name": task.name,
                "algorithm_type": "exam_pipeline",
                "algorithm_code": "exam_pipeline",
                "algorithm_id": None,
                "camera": {
                    "id": camera.id,
                    "rtsp_url": camera.get_rtsp_url(),
                    "mount_position": normalize_mount_position(camera.mount_position),
                },
                "models": models,
                "parameters": {
                    "confidence": task.confidence,
                    "alertThreshold": task.alertThreshold,
                    "algorithm_parameters": task.algorithm_parameters,
                    "inferFps": min(fps_values) if fps_values else 5,
                    "schedule_start": task.schedule_start,
                    "schedule_end": task.schedule_end,
                },
            }

            from app.services.mqtt_service import mqtt_service
            mqtt_service.publish_task_start(edge_node.mac_address, task_payload)

            task.status = 'syncing'
            task.run_status = 'starting'
            if task.has_schedule():
                task.schedule_paused = False
            current_app.logger.info(
                f"Published exam pipeline task {task.id} to edge node {edge_node.mac_address} "
                f"models={list(models.keys())}"
            )
            db.session.commit()
            return {"success": True, "message": "Task start command sent to edge node"}
        except Exception as e:
            import traceback
            current_app.logger.error(f"Error starting exam pipeline: {str(e)}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def stop_detection(self, task_id, *, pause_schedule=None):
        """停止检测任务（下发给边缘计算节点）"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"success": False, "message": "Task not found"}

            task.status = 'stopped'
            task.run_status = 'stopped'
            # pause_schedule=True：用户手动停止，不再自动拉起
            # pause_schedule=False：调度器按时段停止，次日仍可自动启动
            # None：若为定时任务则视为手动暂停
            if pause_schedule is True or (pause_schedule is None and task.has_schedule()):
                task.schedule_paused = True
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
