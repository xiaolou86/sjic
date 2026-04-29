import paho.mqtt.client as mqtt
import json
import logging
import uuid
import os
from flask import current_app
from app.extensions import db
from app.models.edge_node import EdgeNode
from app.models.task import Task
from datetime import datetime

logger = logging.getLogger(__name__)

class MqttService:
    def __init__(self):
        # 生成基于 PID 和 UUID 的唯一客户端 ID 
        # 防止 Flask 在 Debug 热更模式下启动多个进程导致 MQTT 断线互踢（无限循环打印 connected）
        unique_client_id = f"sjic-platform-master-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.client = mqtt.Client(client_id=unique_client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.app = None

    def init_app(self, app):
        self.app = app
        # 这里暂时写死或从 config 取
        broker_ip = app.config.get('MQTT_BROKER_URL', '127.0.0.1')
        broker_port = app.config.get('MQTT_BROKER_PORT', 1883)
        try:
            self.client.connect(broker_ip, broker_port, 60)
            self.client.loop_start()  # 后台线程接收消息
            logger.info(f"Connected to MQTT broker at {broker_ip}:{broker_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {str(e)}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected successfully")
            # 订阅来自所有边缘节点的消息
            client.subscribe("sjic/edge/#")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        logger.debug(f"Received MQTT message on {topic}: {payload}")
        
        try:
            data = json.loads(payload)
            # 处理心跳: sjic/edge/{mac}/heartbeat
            if topic.endswith('/heartbeat'):
                self._handle_heartbeat(data)
            # 处理任务状态反馈: sjic/edge/{mac}/task/status
            elif topic.endswith('/task/status'):
                self._handle_task_status(data)
        except Exception as e:
            logger.error(f"Error processing MQTT message: {str(e)}")

    def _handle_heartbeat(self, data):
        if not self.app:
            return
        with self.app.app_context():
            mac = data.get('edge_id')
            if not mac:
                return
            
            try:
                node = EdgeNode.query.filter_by(mac_address=mac).first()
                if not node:
                    # 自动注册新的边缘节点
                    node = EdgeNode(
                        mac_address=mac,
                        name=data.get('edge_name', f"Edge-{mac[-5:]}"),
                        status='online',
                        architecture=data.get('architecture', '-'),
                        ip_address=data.get('ip_address', '-')
                    )
                    db.session.add(node)
                    db.session.commit() # 提前 commit 防止不同步
                    logger.info(f"Auto-registered new edge node: {mac}")
                
                reported_status = data.get('status', 'online')
                # 不用心跳里的 edge_name 覆盖已存在节点名称，避免覆盖前端手工改名
                if not node.name or not str(node.name).strip():
                    node.name = data.get('edge_name', node.name)
                node.ip_address = data.get('ip_address', node.ip_address)
                node.architecture = data.get('architecture', node.architecture)
                node.status = reported_status
                node.last_heartbeat = datetime.now()
                node.hardware_status = data.get('hardware', {})
                
                # 同步任务状态
                reported_task_ids = [int(tid) for tid in data.get('running_tasks', [])]
                db_running_tasks = Task.query.filter(
                    Task.edge_node_id == node.id,
                    Task.status.in_(['running', 'syncing', 'starting'])
                ).all()
                
                for t in db_running_tasks:
                    # 如果盒子显式汇报离线，或心跳列表里没这个任务，则视为停止
                    if reported_status == 'offline' or t.id not in reported_task_ids:
                        logger.warning(f"Task {t.id} stopped on node {mac} (Cause: {reported_status})")
                        t.status = 'stopped'
                        t.run_status = 'stopped'

                db.session.commit()
            except Exception as e:
                # 捕获并发心跳导致的并发插入冲突 (UNIQUE constraint failed)
                db.session.rollback()
                logger.warning(f"Concurrent insert constraint fallback for {mac}")
                # 冲突说明已经被别的线程插入，退回纯更新模式
                node = EdgeNode.query.filter_by(mac_address=mac).first()
                if node:
                    node.status = 'online'
                    node.last_heartbeat = datetime.now()
                    node.hardware_status = data.get('hardware', {})
                    db.session.commit()

    def _handle_task_status(self, data):
        """更新任务在云端的运行状态反馈"""
        if not self.app:
            return
            
        with self.app.app_context():
            task_id = data.get('task_id')
            status = data.get('status') # running, stopped, error
            message = data.get('message', '')
            
            if not task_id:
                return
                
            try:
                task = Task.query.get(task_id)
                if task:
                    task.run_status = status
                    # 同时更新主状态，确保 UI 反应一致
                    task.status = status 
                    db.session.commit()
                    logger.info(f"Task {task_id} status updated to {status}: {message}")
                    
                    # 如果有 SocketIO，这里可以实时推给前端刷新列表状态
                    try:
                        from app.extensions import socketio
                        socketio.emit('task_status_change', {
                            "task_id": task_id,
                            "run_status": status,
                            "message": message
                        })
                    except ImportError:
                        pass
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating task status: {str(e)}")

    def publish_task_start(self, mac_address, task_payload):
        """下发任务配置到盒子"""
        topic = f"sjic/edge/{mac_address}/task/start"
        self.client.publish(topic, json.dumps(task_payload), qos=1)
        logger.info(f"Published task start to {mac_address}")

    def publish_task_stop(self, mac_address, task_id):
        """下发停止任务指令"""
        topic = f"sjic/edge/{mac_address}/task/stop"
        self.client.publish(topic, json.dumps({"task_id": task_id}), qos=1)
        logger.info(f"Published task stop {task_id} to {mac_address}")

# 创建单例
mqtt_service = MqttService()
