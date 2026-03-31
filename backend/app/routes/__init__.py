"""
路由注册模块。
在 create_app() 中调用 register_blueprints() 完成所有蓝图注册。
"""
from app.routes.camera_routes import camera_bp
from app.routes.model_routes import model_bp
from app.routes.detection_routes import detection_bp
from app.routes.alert_routes import alert_bp
from app.routes.task_routes import task_bp
from app.routes.training_routes import training_bp
from app.routes.stream_routes import stream_bp, create_error_image
from app.routes.setting_routes import setting_bp
from app.routes.algorithm_routes import algorithm_bp
from app.routes.log_routes import log_bp
from app.routes.auth_routes import auth_bp


def register_blueprints(app):
    """注册所有蓝图到 Flask 应用"""
    app.register_blueprint(camera_bp)
    app.register_blueprint(model_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(alert_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(training_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(setting_bp)
    app.register_blueprint(algorithm_bp)
    app.register_blueprint(log_bp)
    app.register_blueprint(auth_bp)

    # 在应用启动时创建错误图像
    create_error_image()

    app.logger.info('All blueprints registered')
