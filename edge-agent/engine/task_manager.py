import logging
import threading
import time
import requests
import os
import cv2
from algorithms import get_algorithm

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, config):
        self.config = config
        self.active_tasks = {}    # task_id -> thread metadata
        self.stop_events = {}     # task_id -> threading.Event()
        self.mqtt_client = None   # 将被注入
        self.api_base_url = self.config['platform']['api_base_url']
        os.makedirs(self.config['paths']['models_dir'], exist_ok=True)

    def set_mqtt_client(self, client):
        self.mqtt_client = client

    def start_task(self, task_config):
        """解析云端指令并启动推理流"""
        task_id = task_config.get('task_id')
        if not task_id:
            logger.error("start_task failed: no task_id provided")
            return

        if task_id in self.active_tasks:
            logger.warning(f"Task {task_id} is already running.")
            return

        logger.info(f"Initializing task {task_id} ({task_config.get('task_name')})")

        # 1. 检查并下载模型
        model_info = task_config.get('model', {})
        model_path = self._ensure_model_exists(model_info)
        if not model_path:
            self._report_status(task_id, "failed", "Model download failed")
            return

        # 2. 准备运行 (创建线程)
        stop_event = threading.Event()
        self.stop_events[task_id] = stop_event
        
        thread = threading.Thread(
            target=self._run_inference_loop,
            args=(task_id, task_config, model_path, stop_event),
            daemon=True
        )
        self.active_tasks[task_id] = thread
        thread.start()
        
        self._report_status(task_id, "running", "Task started successfully")

    def stop_task(self, task_id):
        if task_id in self.stop_events:
            self.stop_events[task_id].set()
            logger.info(f"Sent stop signal to task {task_id}")
            # 等待结束并在 _run_inference_loop 中清理字典
        else:
            logger.warning(f"Task {task_id} not found or not running.")

    def _ensure_model_exists(self, model_info):
        """如果本地没有 `.engine` 或 `.onnx`，从云端下载"""
        filename = model_info.get('filename')
        download_url = model_info.get('download_url')
        if not filename:
            return None
        
        local_path = os.path.join(self.config['paths']['models_dir'], filename)
        if os.path.exists(local_path):
            return local_path
            
        logger.info(f"Model {filename} not found locally, downloading from {download_url}...")
        try:
            # 流式下载真正的模型（带进度指示更佳）
            logger.info(f"Starting to download {filename} from secure URL...")
            response = requests.get(download_url, stream=True, timeout=10)
            response.raise_for_status()

            # 按块写入文件，避免撑爆内存 (比如 1MB 每次)
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk: 
                        f.write(chunk)
            
            logger.info(f"Downloaded model successfully to {local_path} ({os.path.getsize(local_path)} bytes)")
            return local_path
        except requests.exceptions.HTTPError as he:
            logger.error(f"Download authorization or access failed: HTTP {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Download model failed: {str(e)}")
            return None

    def _run_inference_loop(self, task_id, task_config, model_path, stop_event):
        try:
            logger.info(f"Task {task_id} Inference Loop Started. Model: {model_path}")
            
            rtsp_url = task_config['camera'].get('rtsp_url')
            algo_type = task_config.get('algorithm_type')
            
            algo_instance = get_algorithm(algo_type)
            if not algo_instance:
                raise ValueError(f"Algorithm {algo_type} is not supported on this edge node.")

            # 加载本地视频流/RTSP流
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                raise ConnectionError(f"Cannot open camera stream at {rtsp_url}")

            # 为了后续过程能拿到本地模型地址，注入 config 字典中
            task_config['model_local_path'] = model_path

            # 定义告警回调
            def handle_alert(alert_type, confidence, frame):
                self._upload_alert(task_config['camera']['id'], alert_type, confidence, image_frame=frame)

            # 让纯业务代码接管！彻底剥离调度！
            logger.info(f"Handing over stream {rtsp_url} to algorithm: {algo_type}")
            algo_instance.process(
                camera_stream=cap,
                config_dict=task_config,
                logger=logger,
                stop_event=stop_event,
                on_alert=handle_alert
            )

            # 当 stop_event.is_set() 后，process 循环会退出
            cap.release()
            logger.info(f"Task {task_id} Inference Loop Stopped gracefully.")
            self._report_status(task_id, "stopped", "Task stopped by command")
        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            self._report_status(task_id, "error", str(e))
        finally:
            self._cleanup_task(task_id)

    def _cleanup_task(self, task_id):
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
        if task_id in self.stop_events:
            del self.stop_events[task_id]

    def _report_status(self, task_id, status, message):
        """反向通知云端任务的真实执行状态"""
        if self.mqtt_client:
            payload = {
                "timestamp": int(time.time()),
                "task_id": task_id,
                "status": status,
                "message": message
            }
            self.mqtt_client.publish_task_status(payload)

    def _upload_alert(self, camera_id, alert_type, confidence, image_frame=None, image_path=None):
        """HTTP POST 上传告警到云端"""
        url = f"{self.api_base_url}/alerts"
        try:
            data = {
                "camera_id": camera_id,
                "alert_type": alert_type,
                "confidence": confidence
            }
            files = {}
            # 如果内存里有帧（例如 cv2读取的）或者有本地存储的图片
            if image_path and os.path.exists(image_path):
                files['image'] = open(image_path, 'rb')
            elif getattr(image_frame, 'any', lambda: False)(): # numpy array
                import cv2
                success, encoded_image = cv2.imencode('.jpg', image_frame)
                if success:
                    files['image'] = ('alert.jpg', encoded_image.tobytes(), 'image/jpeg')

            response = requests.post(url, data=data, files=files, timeout=5)
            if response.ok:
                logger.info(f"Alert uploaded successfully, type: {alert_type}")
            else:
                logger.error(f"Failed to upload alert: {response.text}")
                
            # 清理打开的文件
            if 'image' in files and hasattr(files['image'], 'close'):
                files['image'].close()
                
        except Exception as e:
            logger.error(f"Exception during alert upload: {str(e)}")
