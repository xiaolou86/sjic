import paho.mqtt.client as mqtt
import json
import logging
import uuid
import os
from flask import current_app
from app.extensions import db
from app.models.edge_node import EdgeNode
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
                        name=f"Edge-{mac[-5:]}",
                        status='online',
                        architecture=data.get('architecture', 'unknown'),
                        ip_address=data.get('ip_address', '')
                    )
                    db.session.add(node)
                    db.session.commit() # 提前 commit 防止不同步
                    logger.info(f"Auto-registered new edge node: {mac}")
                
                node.status = 'online'
                node.last_heartbeat = datetime.now()
                node.hardware_status = data.get('hardware', {})
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
        pass # TODO: 更新任务状态

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
