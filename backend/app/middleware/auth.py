from functools import wraps
from flask import request, jsonify
import jwt
from config import Config


def _extract_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return None

    parts = auth_header.split(' ')
    if len(parts) != 2:
        return None
    return parts[1]


def get_token_payload():
    token = _extract_token()
    if not token:
        return None

    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
    except Exception:
        return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_token_payload()
        if not payload:
            return jsonify({'error': 'Token is missing'}), 401

        return f(*args, **kwargs)

    return decorated 


def role_required(*roles):
    allowed_roles = set(roles)

    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            payload = get_token_payload()
            if not payload:
                return jsonify({'error': 'Token is invalid'}), 401

            role = payload.get('role')
            if role not in allowed_roles:
                return jsonify({'error': 'Permission denied'}), 403

            return f(*args, **kwargs)

        return decorated

    return wrapper