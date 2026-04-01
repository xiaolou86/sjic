"""
系统设置路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import Setting
from app.middleware.auth import token_required

setting_bp = Blueprint('setting', __name__)


@setting_bp.route('/api/settings', methods=['GET'])
@token_required
def get_settings():
    """
    获取系统全局设置
    ---
    tags:
      - 系统设置 (Settings)
    summary: 获取配置参数
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: 系统配置 JSON
    """
    try:
        settings = Setting.query.first()
        if not settings:
            settings = Setting()  # 使用默认值
            db.session.add(settings)
            db.session.commit()
        return jsonify(settings.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error getting settings: {str(e)}")
        return jsonify({'error': str(e)}), 500


@setting_bp.route('/api/settings', methods=['POST'])
@token_required
def update_settings():
    """
    更新系统设置
    ---
    tags:
      - 系统设置 (Settings)
    summary: 全量更新系统设置
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: 设置更新成功
    """
    try:
        data = request.get_json()
        current_app.logger.info(f"Received settings update: {data}")

        settings = Setting.query.first()
        if not settings:
            settings = Setting()
            db.session.add(settings)

        # 更新设置
        settings.update(data)

        # 提交更改
        try:
            db.session.commit()
            current_app.logger.info("Settings committed to database")

            # 验证更新
            updated_settings = Setting.query.get(settings.id)
            current_app.logger.info(f"Verified settings after commit: {updated_settings.config}")

            return jsonify({'message': 'Settings updated successfully'})
        except Exception as e:
            current_app.logger.error(f"Error committing settings: {str(e)}")
            db.session.rollback()
            raise

    except Exception as e:
        current_app.logger.error(f"Error updating settings: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
