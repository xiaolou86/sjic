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

def resolve_sqlite_uri(uri_str):
    """解析 SQLite URI，处理相对路径并确保父目录存在"""
    if not uri_str or not uri_str.startswith('sqlite:'):
        return uri_str

    # 提取文件路径
    raw_path = uri_str.replace('sqlite:////', '/').replace('sqlite:///', '').replace('sqlite://', '')
    if not raw_path or raw_path == ':memory:':
        return uri_str

    # 判断是否为绝对路径
    if os.path.isabs(raw_path) or (len(raw_path) > 1 and raw_path[1] == ':'):
        abs_path = raw_path
    else:
        abs_path = os.path.abspath(os.path.join(base_dir, raw_path))

    # 确保数据库所在目录存在
    db_dir = os.path.dirname(abs_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    clean_path = abs_path.replace('\\', '/')
    if os.name == 'nt' or (len(clean_path) > 1 and clean_path[1] == ':'):
        return f"sqlite:///{clean_path}"
    else:
        return f"sqlite:////{clean_path.lstrip('/')}"

# 强制 SQLite 无论终端在哪级目录启动，默认落地到 backend/instance 目录下
default_sqlite_dir = os.path.join(base_dir, 'instance')
os.makedirs(default_sqlite_dir, exist_ok=True)
default_sqlite_path = os.path.join(default_sqlite_dir, 'app.db')
fallback_uri = resolve_sqlite_uri(f"sqlite:///{default_sqlite_path}")

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or get_cfg('app', 'secret_key', 'your-secret-key')
    
    # MQTT 配置 (支持环境变量与 YAML，Docker 部署时通过 mosquitto 容器名连接)
    MQTT_BROKER_URL = os.environ.get('MQTT_BROKER_URL') or get_cfg('mqtt', 'broker_url', '127.0.0.1')
    MQTT_BROKER_PORT = int(os.environ.get('MQTT_BROKER_PORT') or get_cfg('mqtt', 'broker_port', 38883))
    
    # 动态支持 YAML 配置的 DB 或环境变量覆写
    yaml_uri = get_cfg('database', 'uri')
    env_uri = os.environ.get('DATABASE_URL')
    chosen_uri = env_uri or yaml_uri

    if (not chosen_uri) or chosen_uri.strip() == '' or chosen_uri.strip() in ('sqlite:///app.db', 'sqlite:///instance/app.db'):
        chosen_uri = fallback_uri
    else:
        chosen_uri = resolve_sqlite_uri(chosen_uri)

    SQLALCHEMY_DATABASE_URI = chosen_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False


    # 仅开发应急：为 true 时启动时 db.create_all()（生产务必 false，改用 flask db upgrade）
    AUTO_CREATE_DB = os.environ.get('AUTO_CREATE_DB', 'false').lower() in ('1', 'true', 'yes')
    
    # --- 端边云对象存储与模型下发配置 ---
    STORAGE_TYPE = os.environ.get('STORAGE_TYPE') or get_cfg('storage', 'type', 'NGINX')

    # NGINX secure_link 密钥（须与 frontend 容器 DOWNLOAD_SECURE_KEY 一致）
    DOWNLOAD_SECURE_KEY = os.environ.get('DOWNLOAD_SECURE_KEY') or get_cfg(
        'storage', 'download_secure_key', 'my-super-secret-key-for-nginx'
    )

    # MinIO / OBS
    STORAGE_ENDPOINT = os.environ.get('STORAGE_ENDPOINT') or get_cfg('storage', 'endpoint', 'http://127.0.0.1:9000')
    STORAGE_ACCESS_KEY = os.environ.get('STORAGE_ACCESS_KEY') or get_cfg('storage', 'access_key', 'minioadmin')
    STORAGE_SECRET_KEY = os.environ.get('STORAGE_SECRET_KEY') or get_cfg('storage', 'secret_key', 'minioadmin')
    STORAGE_BUCKET = os.environ.get('STORAGE_BUCKET') or get_cfg('storage', 'bucket', 'sjic-models')

    # 文件存储配置 (基础路径魔法变量)
    UPLOAD_FOLDER = os.path.join(base_dir, 'models')
    ALLOWED_EXTENSIONS = {'pt', 'pth', 'weights', 'engine', 'onnx', 'rknn', 'mtnn'}
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