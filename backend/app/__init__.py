"""
Flask 应用工厂模块。
使用 create_app() 创建应用实例，避免模块导入时产生全局副作用。
"""
import os
import tempfile
import shutil
from flask import Flask
from config import Config
from app.extensions import db, migrate, socketio, cors, sock
from app.logging_config import configure_logging


def create_app(config_class=Config):
    """
    创建并配置 Flask 应用实例。

    Args:
        config_class: 配置类，默认使用 Config

    Returns:
        配置完成的 Flask 应用实例
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 设置最大内容长度
    app.config['MAX_CONTENT_LENGTH'] = config_class.MAX_CONTENT_LENGTH

    # ---- 初始化日志 ----
    configure_logging(app)

    # ---- 初始化扩展 ----
    # CORS
    cors.init_app(app, resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": 86400
        },
        r"/ws/*": {"origins": "*"}
    })

    # 数据库
    db.init_app(app)
    migrate.init_app(app, db)

    # SocketIO
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        logger=True,
        engineio_logger=True
    )

    # Flask-Sock (WebSocket)
    sock.init_app(app)

    # ---- 环境检查 ----
    temp_dir = tempfile.gettempdir()
    app.logger.info(f"Using temporary directory: {temp_dir}")

    if not os.access(temp_dir, os.W_OK):
        app.logger.warning(f"Temporary directory {temp_dir} is not writable!")

    total, used, free = shutil.disk_usage(temp_dir)
    app.logger.info(f"Disk space: total={total//(1024**3)}GB, used={used//(1024**3)}GB, free={free//(1024**3)}GB")

    # 确保模型目录存在
    model_folder = app.config.get('MODEL_FOLDER', config_class.MODEL_FOLDER)
    os.makedirs(model_folder, exist_ok=True)
    app.logger.info(f"Model upload directory: {os.path.abspath(model_folder)}")

    if not os.access(model_folder, os.W_OK):
        app.logger.warning(f"Model upload directory {model_folder} is not writable!")

    # ---- 注册蓝图 & 初始化 ----
    with app.app_context():
        app.logger.info('Initializing application...')

        # 注册所有蓝图
        from app.routes import register_blueprints
        register_blueprints(app)

        # 导入模型以确保表能被创建
        from app.models import camera, detection_model, alert, task, log  # noqa: F401
        from app.algorithms.base import BaseAlgorithm

        # 创建数据库表
        db.create_all()
        app.logger.info('Database tables created')

        # 注册算法
        BaseAlgorithm.register_algorithms()
        app.logger.info('Algorithms registered')

        # 注册错误处理器
        _register_error_handlers(app)

    return app


def _register_error_handlers(app):
    """注册全局错误处理器"""

    @app.errorhandler(404)
    def not_found_error(error):
        from flask import jsonify
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import jsonify
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500