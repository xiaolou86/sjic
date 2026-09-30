"""
系统设置路由蓝图
"""
import os
import uuid
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Setting
from app.middleware.auth import token_required, role_required

setting_bp = Blueprint('setting', __name__)

ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
ALLOWED_UI_THEMES = {'night-tech', 'exam-dawn', 'highway-navy', 'proctor-light'}


def _branding_folder():
    folder = current_app.config.get('BRANDING_FOLDER')
    os.makedirs(folder, exist_ok=True)
    return folder


def _branding_payload(config):
    branding = (config or {}).get('branding') or {}
    logo_filename = branding.get('logo_filename') or ''
    logo_url = f'/api/branding/logo/{logo_filename}' if logo_filename else ''
    system = (config or {}).get('system') or {}
    ui_theme = system.get('ui_theme') or 'night-tech'
    if ui_theme not in ALLOWED_UI_THEMES:
        ui_theme = 'night-tech'
    return {
        'company_name': branding.get('company_name') or '',
        'product_name': branding.get('product_name') or '智算检测平台',
        'logo_filename': logo_filename,
        'logo_url': logo_url,
        'ui_theme': ui_theme,
    }


def _get_or_create_settings():
    settings = Setting.query.first()
    if not settings:
        settings = Setting()
        db.session.add(settings)
        db.session.commit()
    return settings


@setting_bp.route('/api/settings', methods=['GET'])
@token_required
def get_settings():
    """获取系统全局设置"""
    try:
        settings = _get_or_create_settings()
        return jsonify(settings.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error getting settings: {str(e)}")
        return jsonify({'error': str(e)}), 500


@setting_bp.route('/api/settings', methods=['POST'])
@token_required
def update_settings():
    """更新系统设置（品牌相关字段仅服务商超管可改）"""
    try:
        data = request.get_json() or {}
        # 密码哈希只允许走 /api/auth/password，避免保存设置时被覆盖
        data.pop('accounts', None)
        current_app.logger.info(f"Received settings update: {data}")

        from app.middleware.auth import get_token_payload
        payload = get_token_payload() or {}
        role = payload.get('role')

        # 非 vendor 不可改 branding；避免被静默改掉
        if 'branding' in data and role != 'vendor':
            data = {k: v for k, v in data.items() if k != 'branding'}

        system = data.get('system')
        if isinstance(system, dict) and 'ui_theme' in system:
            if system.get('ui_theme') not in ALLOWED_UI_THEMES:
                system['ui_theme'] = 'night-tech'

        settings = _get_or_create_settings()
        settings.update(data)
        db.session.commit()
        current_app.logger.info("Settings committed to database")
        return jsonify({'message': 'Settings updated successfully', 'config': settings.to_dict()})
    except Exception as e:
        current_app.logger.error(f"Error updating settings: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@setting_bp.route('/api/branding', methods=['GET'])
def get_branding():
    """公开品牌信息（登录页无需鉴权）"""
    try:
        settings = Setting.query.first()
        config = settings.to_dict() if settings else Setting.merged_config()
        return jsonify(_branding_payload(config))
    except Exception as e:
        current_app.logger.error(f"Error getting branding: {str(e)}")
        return jsonify(_branding_payload(Setting.DEFAULT_CONFIG))


@setting_bp.route('/api/branding/logo/<path:filename>', methods=['GET'])
def get_branding_logo(filename):
    """公开 Logo 文件"""
    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({'error': 'Not found'}), 404
    folder = _branding_folder()
    path = os.path.join(folder, safe_name)
    if not os.path.isfile(path):
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(folder, safe_name)


@setting_bp.route('/api/settings/logo', methods=['POST'])
@token_required
@role_required('vendor')
def upload_logo():
    """上传品牌 Logo（仅服务商超管）"""
    try:
        if 'logo' not in request.files:
            return jsonify({'error': 'No logo file'}), 400
        file = request.files['logo']
        if not file or not file.filename:
            return jsonify({'error': 'Empty filename'}), 400

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ALLOWED_LOGO_EXTENSIONS:
            return jsonify({'error': f'Unsupported format: {ext}'}), 400

        folder = _branding_folder()
        filename = f"logo_{uuid.uuid4().hex[:12]}.{ext}"
        file.save(os.path.join(folder, filename))

        settings = _get_or_create_settings()
        old = (settings.config or {}).get('branding', {}).get('logo_filename')
        settings.update({'branding': {'logo_filename': filename}})
        db.session.commit()

        # 清理旧 logo（忽略失败）
        if old and old != filename:
            try:
                old_path = os.path.join(folder, secure_filename(old))
                if os.path.isfile(old_path):
                    os.remove(old_path)
            except OSError:
                pass

        branding = _branding_payload(settings.to_dict())
        return jsonify({'message': 'Logo uploaded', 'branding': branding})
    except Exception as e:
        current_app.logger.error(f"Error uploading logo: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@setting_bp.route('/api/settings/logo', methods=['DELETE'])
@token_required
@role_required('vendor')
def delete_logo():
    """清除品牌 Logo（仅服务商超管）"""
    try:
        settings = _get_or_create_settings()
        branding = (settings.config or {}).get('branding') or {}
        old = branding.get('logo_filename')
        settings.update({'branding': {'logo_filename': ''}})
        db.session.commit()

        if old:
            try:
                path = os.path.join(_branding_folder(), secure_filename(old))
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass

        return jsonify({'message': 'Logo removed', 'branding': _branding_payload(settings.to_dict())})
    except Exception as e:
        current_app.logger.error(f"Error deleting logo: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
