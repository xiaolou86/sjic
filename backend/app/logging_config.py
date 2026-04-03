"""
日志配置模块。
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from config import Config


def configure_logging(app):
    """为 Flask 应用配置统一规范的日志处理器，防重复"""
    os.makedirs(Config.LOG_FOLDER, exist_ok=True)
    formatter = logging.Formatter(Config.LOG_FORMAT)

    file_handler = RotatingFileHandler(
        Config.LOG_PATH,
        maxBytes=Config.LOG_MAX_BYTES,
        backupCount=Config.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(Config.LOG_LEVEL)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(Config.LOG_LEVEL)

    # 1. 彻底清空 Flask app自带的默认花里胡哨的 handler (如 DEBUG in module)
    for h in app.logger.handlers[:]:
        app.logger.removeHandler(h)
    app.logger.propagate = True # 让 Flask 乖乖把日志传给上帝 Root Logger

    # 2. 配置上帝节点：根日志器 (Root Logger)
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.setLevel(Config.LOG_LEVEL)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 防止 werkzeug 和 engineio 刷屏
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)
