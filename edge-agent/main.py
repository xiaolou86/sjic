import yaml
import time
import os
import logging
import psutil
import socket

from utils.ip import get_mac_address, get_local_ip_address
from mqtt_client import EdgeMqttClient
from engine.task_manager import TaskManager
from platforms import get_platform_info

# 设置环境变量，优化 OpenCV FFmpeg 读取性能，防止出现 grabFrame packet read max attempts exceeded
os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "16384"


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
    """获取设备状态（支持多平台硬件信息采集）"""
    base = {
        "cpu_usage": psutil.cpu_percent(),
        "mem_usage": psutil.virtual_memory().percent,
    }
    # 合并平台特定的硬件信息（温度、NPU 状态等）
    base.update(get_platform_info(architecture))
    return base

def main():
    config = load_config()
    arch = config.get('architecture', 'x86')
    logger.info(f"Starting SJIC Edge Agent [{config['edge_name']}] [{config['edge_id']}] on platform: {arch}")

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

    # 4. 守护循环：周期推送心跳与信号监听
    import signal
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        logger.info(f"Received exit signal ({signum}), gracefully shutting down edge agent...")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_signal)

    while running:
        try:
            # 构建心跳负荷
            heartbeat_payload['timestamp'] = int(time.time())
            heartbeat_payload['hardware'] = get_hardware_status(arch)
            heartbeat_payload['status'] = "online"
            heartbeat_payload['running_tasks'] = list(task_manager.active_tasks.keys())
            mqtt_client.publish_heartbeat(heartbeat_payload)
            logger.debug("Heartbeat sent.")
        except Exception as loop_err:
            logger.error(f"Error in heartbeat loop: {loop_err}", exc_info=True)

        # 步进 sleep（每秒检测 running 标志，支持秒级响应退出信号）
        for _ in range(30):
            if not running:
                break
            time.sleep(1)

    logger.info("Shutting down edge agent...")
    mqtt_client.stop()

if __name__ == "__main__":
    main()
