import os
from datetime import datetime

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 文件存储配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'models')
    ALLOWED_EXTENSIONS = {'pt', 'pth', 'weights', 'engine', 'onnx'}
    
    # 模型配置
    MODEL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
    
    # --- 端边云对象存储与模型下发配置 ---
    # 支持: 'MINIO', 'OBS', 'NGINX'
    STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'NGINX')
    
    # 针对 Nginx: 代理的静态基础路径及下载签名密钥
    NGINX_STATIC_BASE_URL = os.environ.get('NGINX_STATIC_BASE_URL', 'http://127.0.0.1/static-models')
    DOWNLOAD_SECURE_KEY = os.environ.get('DOWNLOAD_SECURE_KEY', 'my-super-secret-key-for-nginx')
    
    # 针对 MinIO / OBS: API凭证和 Endpoint
    STORAGE_ENDPOINT = os.environ.get('STORAGE_ENDPOINT', 'http://192.168.1.10:9000')
    STORAGE_ACCESS_KEY = os.environ.get('STORAGE_ACCESS_KEY', 'minioadmin')
    STORAGE_SECRET_KEY = os.environ.get('STORAGE_SECRET_KEY', 'minioadmin')
    STORAGE_BUCKET = os.environ.get('STORAGE_BUCKET', 'sjic-models')
    
    # 视频源配置
    VIDEO_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'videos')

    # 前端标定后的图像
    IMAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')

    ALERT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alerts')

    # 日志配置
    LOG_FOLDER = 'logs'
    LOG_FILENAME = f'app_{datetime.now().strftime("%Y%m%d")}.log'
    LOG_PATH = os.path.join(LOG_FOLDER, LOG_FILENAME)
    LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    LOG_LEVEL = 'DEBUG'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 10  # 保留10个备份文件
    
    # 区域配置存储
    REGION_CONFIG_PATH = 'data/regions.json'
    
    # 端口配置
    #FRONTEND_PORT = 38880
    BACKEND_PORT = 38881
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB
    
    # CORS 配置
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')  # 默认允许所有
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_HEADERS = ['Content-Type', 'Authorization'] 