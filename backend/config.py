import os
import yaml
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))

# 尝试加载 config.yaml
yaml_path = os.path.join(base_dir, 'config.yaml')
yaml_cfg = {}
if os.path.exists(yaml_path):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        yaml_cfg = yaml.safe_load(f) or {}

def get_cfg(section, key, default=None):
    return yaml_cfg.get(section, {}).get(key, default)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or get_cfg('app', 'secret_key', 'your-secret-key')
    
    # 动态支持 YAML 配置的 DB 或环境变量覆写
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or get_cfg('database', 'uri', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- 端边云对象存储与模型下发配置 ---
    STORAGE_TYPE = os.environ.get('STORAGE_TYPE') or get_cfg('storage', 'type', 'NGINX')
    
    # NGINX
    NGINX_STATIC_BASE_URL = os.environ.get('NGINX_STATIC_BASE_URL') or get_cfg('storage', 'nginx_static_base_url', 'http://127.0.0.1/static-models')
    DOWNLOAD_SECURE_KEY = os.environ.get('DOWNLOAD_SECURE_KEY') or get_cfg('storage', 'download_secure_key', 'super-secret')
    
    # MinIO / OBS
    STORAGE_ENDPOINT = os.environ.get('STORAGE_ENDPOINT') or get_cfg('storage', 'endpoint', 'http://127.0.0.1:9000')
    STORAGE_ACCESS_KEY = os.environ.get('STORAGE_ACCESS_KEY') or get_cfg('storage', 'access_key', 'minioadmin')
    STORAGE_SECRET_KEY = os.environ.get('STORAGE_SECRET_KEY') or get_cfg('storage', 'secret_key', 'minioadmin')
    STORAGE_BUCKET = os.environ.get('STORAGE_BUCKET') or get_cfg('storage', 'bucket', 'sjic-models')

    # 文件存储配置 (基础路径魔法变量)
    UPLOAD_FOLDER = os.path.join(base_dir, 'models')
    ALLOWED_EXTENSIONS = {'pt', 'pth', 'weights', 'engine', 'onnx'}
    # 模型文件
    MODEL_FOLDER = os.path.join(base_dir, 'models')
    # 视频源
    VIDEO_FOLDER = os.path.join(base_dir, 'videos')
    # 前端标定后的图像
    IMAGE_FOLDER = os.path.join(base_dir, 'images')

    # 优先读取 YAML 中的自定义告警存储路径，为空则回落到默认的 `alerts` 文件夹
    custom_alert_path = get_cfg('fs', 'alert_storage_path')
    if custom_alert_path and custom_alert_path.strip():
        ALERT_FOLDER = custom_alert_path
    else:
        ALERT_FOLDER = os.environ.get('ALERT_STORAGE_PATH') or os.path.join(base_dir, 'alerts')

    # 日志配置
    LOG_FOLDER = 'logs'
    LOG_FILENAME = f'app_{datetime.now().strftime("%Y%m%d")}.log'
    LOG_PATH = os.path.join(LOG_FOLDER, LOG_FILENAME)
    LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    LOG_LEVEL = 'DEBUG'
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 10
    
    REGION_CONFIG_PATH = 'data/regions.json'
    BACKEND_PORT = 38881
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024
    
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS') \
        or get_cfg('security', 'cors_origins', '*')
    CORS_ORIGINS = CORS_ORIGINS.split(',')
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_HEADERS = ['Content-Type', 'Authorization']