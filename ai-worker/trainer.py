import os
import shutil
import zipfile
import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class Trainer:
    def __init__(self, output_dir="./data/models"):
        self.model = None
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
            
    def extract_dataset(self, zip_path, target_dir):
        """解压从后台下发的数据集包"""
        os.makedirs(target_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        return target_dir
        
    def train(self, zip_path, task_config):
        try:
            # 1. 解压数据集
            extract_folder = os.path.join(os.path.dirname(zip_path), "dataset_extracted")
            if os.path.exists(extract_folder):
                shutil.rmtree(extract_folder)
            
            logger.info(f"Extracting dataset {zip_path} to {extract_folder}...")
            self.extract_dataset(zip_path, extract_folder)
            
            # TODO: 这里需要根据 zip 里的数据格式，动态构建一个 dataset.yaml 供 YOLO 读取。
            # 为了演示，我们假设根目录下带有一个 data.yaml 
            yaml_path = os.path.join(extract_folder, "data.yaml")
            
            if not os.path.exists(yaml_path):
                raise FileNotFoundError("data.yaml not found inside dataset root.")

            # 2. 初始化YOLO网络结构
            self.model = YOLO('yolov8n.pt')
            
            # 3. 开始消耗极大的 GPU 训练资源...
            logger.info(f"Starting heavy PyTorch YOLO training loop. Epochs: {task_config.get('epochs', 10)}")
            results = self.model.train(
                data=yaml_path,
                epochs=task_config.get('epochs', 10),
                batch=task_config.get('batchSize', 16),
                imgsz=640,
                save=True,
                project=self.output_dir,
                name=task_config.get('name', 'custom')
            )
            
            # TODO: 训练完毕后，需要把 results.save_dir 里面的 best.pt 上传回 OBS 或 MinIO
            # 我们在这个范例里仅仅返回在本地 worker 上的模型存储路径。
            
            return {
                'success': True,
                'message': 'Model training complete',
                'model_local_path': str(results.save_dir)
            }
            
        except Exception as e:
            logger.error(f"Error during training: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
