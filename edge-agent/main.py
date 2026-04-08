import yaml
import time
import os
import logging
import psutil
import uuid

# 设置环境变量，优化 OpenCV FFmpeg 读取性能，防止出现 grabFrame packet read max attempts exceeded
os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "16384"

from mqtt_client import EdgeMqttClient
from engine.task_manager import TaskManager
# 修改日志格式：使用标准的层级化日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

logger = logging.getLogger('edge')

def get_mac_address():
    """获取设备的真实物理常驻 MAC 地址作为默认唯一硬件标识"""
    mac_num = hex(uuid.getnode()).replace('0x', '').replace('L', '').zfill(12).upper()
    return '-'.join(mac_num[i: i + 2] for i in range(0, 12, 2))

def load_config(path='config.yaml'):
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
        
    # 如果配置文件没有指定 edge_id，则自动读取本机的 MAC 地址作为默认 ID
    if not config.get('edge_id') or config.get('edge_id') == "":
        config['edge_id'] = get_mac_address()
        
    return config

def get_hardware_status():
    """获取设备状态"""
    return {
        "cpu_usage": psutil.cpu_percent(),
        "mem_usage": psutil.virtual_memory().percent,
        # TODO: 读取特定平台的温度或 NPU 占用，如 Rk3588 cat /sys/class/thermal/thermal_zone0/temp
        "temperature": 50.0 
    }

def main():
    config = load_config()
    logger.info(f"Starting SJIC Edge Agent [{config['edge_id']}]")

    # 1. 实例化任务管理器 (负责 AI 推理全生命周期)
    task_manager = TaskManager(config)

    # 2. 实例化并启动 MQTT (负责云边通信)
    mqtt_client = EdgeMqttClient(config, task_manager)
    task_manager.set_mqtt_client(mqtt_client) # 反向注入以便发状态
    mqtt_client.start()

    # 3. 守护循环：周期推送心跳
    try:
        while True:
            # 构建心跳负荷
            heartbeat_payload = {
                "timestamp": int(time.time()),
                "edge_id": config['edge_id'],
                "architecture": config['architecture'],
                "status": "online",
                "hardware": get_hardware_status(),
                "running_tasks": list(task_manager.active_tasks.keys())
            }
            mqtt_client.publish_heartbeat(heartbeat_payload)
            logger.debug(f"Heartbeat sent.")
            time.sleep(30) # 每30秒发送一次心跳
            
    except KeyboardInterrupt:
        logger.info("Shutting down edge agent...")
        mqtt_client.stop()

if __name__ == "__main__":
    main()
