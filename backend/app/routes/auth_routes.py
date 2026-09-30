"""
认证路由蓝图
"""
from flask import Blueprint, jsonify, request, make_response, current_app
from flask_cors import cross_origin
import jwt
from datetime import datetime, timedelta
from config import Config
from app.extensions import db
from app.middleware.auth import token_required, get_token_payload
from app.models import Setting
from app.services.accounts import (
    BUILTIN_ACCOUNTS,
    MIN_PASSWORD_LENGTH,
    authenticate,
    hash_password,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/login', methods=['POST', 'OPTIONS'])
@cross_origin(origins="*", methods=['POST', 'OPTIONS'], supports_credentials=True)
def login():
    """
    管理员登录
    ---
    tags:
      - 认证 (Auth)
    summary: 登录获取 JWT Token
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
            password:
              type: string
    responses:
      200:
        description: 登录成功，返回 token 和用户信息
      401:
        description: 用户名或密码错误
    """
    current_app.logger.info(f"Login request received: method={request.method}")

    # 处理预检请求
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
        return response

    # 处理实际的登录请求
    data = request.json
    username = data.get('username')
    password = data.get('password')

    current_app.logger.info(f"Processing login for username: {username}")

    settings = Setting.query.first()
    role = authenticate(username, password, settings.config if settings else None)

    if role:
        token = jwt.encode({
            'user': username,
            'role': role,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, Config.SECRET_KEY, algorithm='HS256')
        
        # 兼容旧版本 PyJWT 的 bytes 返还值问题，如果是 bytes 就转换成字符串
        if isinstance(token, bytes):
            token = token.decode('utf-8')

        response = jsonify({
            'token': token,
            'username': username,
            'role': role
        })
        return response

    return jsonify({'error': 'Invalid credentials'}), 401


@auth_bp.route('/api/logout', methods=['POST'])
@token_required
def logout():
    """记录退出登录。审计由 after_request 写入。"""
    return jsonify({'status': 'ok'})


@auth_bp.route('/api/auth/password', methods=['POST'])
@token_required
def change_password():
    """修改当前登录账号的密码。"""
    payload = get_token_payload() or {}
    username = payload.get('user') if isinstance(payload.get('user'), str) else ''
    username = username.strip()
    if username not in BUILTIN_ACCOUNTS:
        return jsonify({'error': '当前账号不支持修改密码'}), 400

    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password') if isinstance(data.get('old_password'), str) else ''
    new_password = data.get('new_password') if isinstance(data.get('new_password'), str) else ''
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'新密码至少 {MIN_PASSWORD_LENGTH} 位'}), 400
    if new_password == old_password:
        return jsonify({'error': '新密码不能与原密码相同'}), 400

    try:
        settings = Setting.query.first()
        if not settings:
            settings = Setting()
            db.session.add(settings)

        if not authenticate(username, old_password, settings.config):
            db.session.rollback()
            return jsonify({'error': '原密码不正确'}), 400

        settings.update({
            'accounts': {
                username: {'password_hash': hash_password(new_password)},
            }
        })
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to change password for {username}: {e}")
        return jsonify({'error': '修改密码失败'}), 500
    return jsonify({'message': '密码已更新，下次登录请使用新密码'})