import yaml
import time
import os
import logging
import psutil
import socket

# 必须在 import cv2 之前设置。只保留 tcp：多余 option 会让部分 OpenCV 丢掉整串参数，仍走 UDP。
os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "65536"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

from utils.ip import get_mac_address, get_local_ip_address
from mqtt_client import EdgeMqttClient
from engine.task_manager import TaskManager
from platforms import get_platform_info, start_gpu_sampler


# 修改日志格式：使用标准的层级化日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

logger = logging.getLogger('edge')


def load_config(path='config.yaml'):
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
        
    # 如果配置文件没有指定 edge_name，则自动读取本机的hostname作为默认名称
    if not config.get('edge_name') or config.get('edge_name') == "":
        config['edge_name'] = socket.gethostname()

    config['edge_id'] = get_mac_address()
        
    return config

def get_hardware_status(architecture):
    """获取设备状态（CPU / 内存 / GPU 或 NPU）"""
    mem = psutil.virtual_memory()
    base = {
        "cpu_usage": psutil.cpu_percent(interval=None),
        "mem_usage": mem.percent,
        "mem_used_mb": round(mem.used / 1024 / 1024),
        "mem_total_mb": round(mem.total / 1024 / 1024),
    }
    try:
        extra = get_platform_info(architecture) or {}
        if isinstance(extra, dict):
            base.update(extra)
    except Exception as e:
        logger.debug(f"platform hardware extras skipped: {e}")
    return base

def main():
    config = load_config()
    arch = config.get('architecture', 'x86')
    logger.info(f"Starting SJIC Edge Agent [{config['edge_name']}] [{config['edge_id']}] on platform: {arch}")
    start_gpu_sampler(arch)

    # 1. 实例化任务管理器 (负责 AI 推理全生命周期)
    task_manager = TaskManager(config)

    # 2. 实例化并启动 MQTT (负责云边通信)
    mqtt_client = EdgeMqttClient(config, task_manager)
    task_manager.set_mqtt_client(mqtt_client) # 反向注入以便发状态
    mqtt_client.start()
    
    # 3. 自动恢复重启前的任务
    task_manager.reload_tasks()

    heartbeat_payload = {
        "timestamp": int(time.time()),
        "edge_id": config['edge_id'],
        "edge_name": config['edge_name'],
        "architecture": arch,
        "status": "online",
        "hardware": get_hardware_status(arch),
        "ip_address": get_local_ip_address(),
    }

    # 4. 守护循环：周期推送心跳
    try:
        while True:
            try:
                heartbeat_payload['timestamp'] = int(time.time())
                heartbeat_payload['hardware'] = get_hardware_status(arch)
                heartbeat_payload['status'] = "online"
                heartbeat_payload['running_tasks'] = list(task_manager.active_tasks.keys())
                mqtt_client.publish_heartbeat(heartbeat_payload)
                logger.debug("Heartbeat sent.")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Shutting down edge agent...")
        mqtt_client.stop()

if __name__ == "__main__":
    main()
