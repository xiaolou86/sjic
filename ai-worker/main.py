import paho.mqtt.client as mqtt
import yaml
import json
import os
import requests
import logging
import threading
from trainer import Trainer

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] AI-WORKER: %(message)s')
logger = logging.getLogger(__name__)

# 读取配置
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# 全局初始化底层炼丹炉
trainer_engine = Trainer(output_dir=config['OUTPUT_DIR'])


def download_dataset(url, download_dir, filename):
    """流水线步骤1：从网关(NGINX/OBS)安全下载拉取数据集ZIP包"""
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, filename)
    
    logger.info(f"Downloading dataset from URL -> {local_path} ...")
    response = requests.get(url, stream=True, timeout=10)
    response.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                
    return local_path


def process_training_job(payload, mqtt_client):
    """真正的异步后台处理协程"""
    job_id = payload.get("job_id")
    dataset_url = payload.get("dataset_url")
    filename = payload.get("filename")
    task_config = payload.get("config", {})
    
    # 广播进度: 开始下载
    mqtt_client.publish(config['STATUS_TOPIC'], json.dumps({"job_id": job_id, "status": "downloading"}))
    
    try:
        # 下载文件
        zip_path = download_dataset(dataset_url, config['DOWNLOAD_DIR'], filename)
        
        # 广播进度: 下载完毕，开始训练
        mqtt_client.publish(config['STATUS_TOPIC'], json.dumps({"job_id": job_id, "status": "training"}))
        
        # 调用核心 Pytorch 代码，这里可能会卡上几十个甚至是几百个小时！
        result = trainer_engine.train(zip_path, task_config)
        
        if result['success']:
            # 广播进度: 训练成功
            mqtt_client.publish(config['STATUS_TOPIC'], json.dumps({
                "job_id": job_id, 
                "status": "completed",
                "model_url": result.get('model_local_path') # TODO: 记得加回传 OBS 逻辑
            }))
        else:
            # 广播错误
            mqtt_client.publish(config['STATUS_TOPIC'], json.dumps({
                "job_id": job_id, 
                "status": "failed",
                "error": result.get('error')
            }))
            
    except Exception as e:
        logger.error(f"Job {job_id} Pipeline crashed: {e}")
        mqtt_client.publish(config['STATUS_TOPIC'], json.dumps({
            "job_id": job_id, 
            "status": "failed",
            "error": str(e)
        }))

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker: {config['MQTT_BROKER']} with result {rc}")
    topic = config['TRAINING_TOPIC']
    client.subscribe(topic)
    logger.info(f"Successfully subscribed to Heavy-Task Queue: {topic}")


def on_message(client, userdata, msg):
    """接到 MQTT 通知，开启新的后台线程（不要阻塞 MQTT 主循环心跳）来进行炼丹"""
    try:
        payload_str = msg.payload.decode('utf-8')
        payload = json.loads(payload_str)
        job_id = payload.get("job_id", "Unknown")
        
        logger.info(f">>> Received new training job: {job_id}")
        
        # 为了防止长达几个小时的训练阻塞了 MQTT 网络心跳保活机制，派发给单独的物理线程执行
        thread = threading.Thread(target=process_training_job, args=(payload, client))
        thread.start()

    except Exception as e:
        logger.error(f"Failed to parse or dispatch incoming job: {str(e)}")


def main():
    client = mqtt.Client(client_id="ai_heavy_worker_node_1")
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info("Initializing Big-Data AI GPU Worker...")
    client.connect(config['MQTT_BROKER'], config['MQTT_PORT'], 60)
    
    # 阻塞永远运行
    client.loop_forever()


if __name__ == "__main__":
    main()
