import logging
import threading
import time
import requests
import os
import cv2
from algorithms import get_algorithm
from runtime import create_runtime

logger = logging.getLogger('engine.task')

class TaskManager:
    def __init__(self, config):
        self.config = config
        self.active_tasks = {}    # task_id -> thread metadata
        self.stop_events = {}     # task_id -> threading.Event()
        self.mqtt_client = None   # 将被注入
        self.api_base_url = self.config['platform']['api_base_url']
        self.persistence_file = os.path.join(self.config['paths']['models_dir'], 'tasks.json')
        os.makedirs(self.config['paths']['models_dir'], exist_ok=True)
        self.active_configs = {}  # task_id -> config dictionary for persistence

        # 根据盒子平台类型创建对应的推理后端（全局共享）
        self.runtime = create_runtime(config['architecture'])
        logger.info(f"TaskManager initialized with runtime for architecture: {config['architecture']}")

    def set_mqtt_client(self, client):
        self.mqtt_client = client

    def start_task(self, task_config, save=True):
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
        self.active_configs[task_id] = task_config
        thread.start()
        
        if save:
            self._save_tasks()

        self._report_status(task_id, "running", "Task started successfully")

    def stop_task(self, task_id):
        if task_id in self.stop_events:
            self.stop_events[task_id].set()
            if task_id in self.active_configs:
                del self.active_configs[task_id]
                self._save_tasks()
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
            def handle_alert(alert_type, confidence, image_frame):
                self._upload_alert(task_config['camera']['id'], alert_type, confidence, image_frame=image_frame)

            # 让纯业务代码接管！彻底剥离调度！
            logger.info(f"Handing over stream {rtsp_url} to algorithm: {algo_type}")
            
            # 为该任务创建一个专用的子日志器
            task_logger = logger.getChild(f"Task-{task_id}.{algo_type}")
            
            # 将 runtime 注入算法 process 方法
            algo_instance.process(
                camera_stream=cap,
                config_dict=task_config,
                logger=task_logger,
                stop_event=stop_event,
                on_alert=handle_alert,
                runtime=self.runtime
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
        # 注意：这里不清 self.active_configs，因为它决定了下次重启是否自启动

    def _save_tasks(self):
        """持久化当前运行的任务配置"""
        try:
            import json
            with open(self.persistence_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.active_configs.values()), f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self.active_configs)} task configs to {self.persistence_file}")
        except Exception as e:
            logger.error(f"Failed to save tasks: {str(e)}")

    def reload_tasks(self):
        """重启后重新加载任务"""
        if not os.path.exists(self.persistence_file):
            return
        
        try:
            import json
            with open(self.persistence_file, 'r', encoding='utf-8') as f:
                configs = json.load(f)
            
            logger.info(f"Found {len(configs)} tasks to resume from persistence.")
            for cfg in configs:
                # 重新启动，但不立即再次保存文件
                self.start_task(cfg, save=False)
        except Exception as e:
            logger.error(f"Failed to reload tasks: {str(e)}")

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
            elif image_frame is not None and hasattr(image_frame, 'any') and image_frame.any():
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
