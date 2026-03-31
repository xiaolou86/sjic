"""
日志配置模块。
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from config import Config


def configure_logging(app):
    """为 Flask 应用配置日志处理器"""
    # 创建日志目录
    os.makedirs(Config.LOG_FOLDER, exist_ok=True)

    # 配置日志格式
    formatter = logging.Formatter(Config.LOG_FORMAT)

    # 文件处理器
    file_handler = RotatingFileHandler(
        Config.LOG_PATH,
        maxBytes=Config.LOG_MAX_BYTES,
        backupCount=Config.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(Config.LOG_LEVEL)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(Config.LOG_LEVEL)

    # 添加处理器到应用
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(Config.LOG_LEVEL)
