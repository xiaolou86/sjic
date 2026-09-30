"""
Flask 应用工厂模块。
使用 create_app() 创建应用实例，避免模块导入时产生全局副作用。
"""
import os
import tempfile
import shutil
from datetime import datetime
from flask import Flask
from config import Config
from app.extensions import db, migrate, socketio, cors, sock
from app.logging_config import configure_logging


def _load_platform_started_at(app):
    """计时落在 instance 卷上。文件已有则沿用；没有则用库里最早记录，避免镜像重建后从零开始。"""
    path = os.path.join(app.instance_path, 'platform_started_at.txt')
    if os.path.isfile(path):
        try:
            raw = open(path, encoding='utf-8').read().strip()
            return datetime.fromisoformat(raw)
        except (OSError, ValueError) as exc:
            app.logger.warning(f"platform_started_at unreadable ({exc}), will rewrite")
    started = datetime.now().replace(microsecond=0)
    try:
        from sqlalchemy import func
        from app.models.algorithm import Algorithm
        from app.models.camera import Camera
        stamps = []
        for model in (Algorithm, Camera):
            stamp = db.session.query(func.min(model.created_at)).scalar()
            if stamp:
                stamps.append(stamp.replace(microsecond=0) if stamp.microsecond else stamp)
        if stamps:
            started = min(stamps + [started])
    except Exception as exc:
        app.logger.info(f"platform uptime seed skipped: {exc}")
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(started.isoformat())
    except OSError as exc:
        app.logger.warning(f"failed to persist platform_started_at: {exc}")
    return started


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
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
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

    # 确保应用核心工作目录与实例目录存在
    os.makedirs(app.instance_path, exist_ok=True)
    app.config['APP_STARTED_AT'] = datetime.now().replace(microsecond=0)
    for folder_key in ['MODEL_FOLDER', 'VIDEO_FOLDER', 'IMAGE_FOLDER', 'ALERT_FOLDER', 'LOG_FOLDER', 'BRANDING_FOLDER']:
        folder_path = app.config.get(folder_key)
        if folder_path:
            os.makedirs(folder_path, exist_ok=True)

    model_folder = app.config.get('MODEL_FOLDER', config_class.MODEL_FOLDER)
    app.logger.info(f"Model upload directory: {os.path.abspath(model_folder)}")

    if not os.access(model_folder, os.W_OK):
        app.logger.warning(f"Model upload directory {model_folder} is not writable!")

    # ---- 注册蓝图 & 初始化 ----
    with app.app_context():
        app.logger.info('Initializing application...')

        # 注册所有蓝图
        from app.routes import register_blueprints
        register_blueprints(app)

        # 注册全部 ORM 模型（供迁移 autogenerate 与运行时一致）
        # 注意：勿写 `import app.models`，会与局部变量 app(Flask 实例) 冲突
        from app import models as _orm_models  # noqa: F401

        app.config['APP_STARTED_AT'] = _load_platform_started_at(app)

        if app.config.get('AUTO_CREATE_DB'):
            app.logger.warning(
                'AUTO_CREATE_DB is enabled; calling db.create_all(). '
                'Prefer: flask db upgrade'
            )
            db.create_all()
        else:
            app.logger.info(
                'Skipping create_all; apply schema with: '
                'FLASK_APP=run.py flask db upgrade'
            )

        try:
            from sqlalchemy import inspect as sa_inspect
            from app.models.algorithm import Algorithm
            if sa_inspect(db.engine).has_table('algorithms'):
                Algorithm.initialize_default_algorithms()
                app.logger.info('Algorithms metadata initialized')
            else:
                app.logger.info(
                    'Skip algorithm seed: run flask db upgrade first'
                )
        except Exception as e:
            app.logger.warning(f"Database inspection skipped: {e}")

        try:
            from app.utils.db_compat import ensure_alert_camera_optional
            ensure_alert_camera_optional()
        except Exception as e:
            app.logger.warning(f"Alert camera_id schema check skipped: {e}")


        # 注册错误处理器
        _register_error_handlers(app)

        # 未授权时拦截业务 API（登录与授权导入除外）
        from app.middleware.license_guard import register_request_guards
        register_request_guards(app)

        from app.services.audit import register_audit
        register_audit(app)

    # 初始化 MQTT
    from app.services.mqtt_service import mqtt_service
    mqtt_service.init_app(app)

    # 定时任务每日时段自动启停
    try:
        from app.services.task_scheduler import start_task_scheduler
        start_task_scheduler(app)
    except Exception as e:
        app.logger.warning(f"Task scheduler not started: {e}")

    # 注册 Swagger
    from flasgger import Swagger
    swagger = Swagger(app)

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