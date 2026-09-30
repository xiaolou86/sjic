"""
Global request guards (license enforcement).
"""
from flask import request, jsonify
from app.services.license_service import license_service


REASON_MESSAGES = {
    'license_required': '尚未导入授权，请先导入试用版或正式版授权文件',
    'license_expired': '授权已过期',
    'machine_mismatch': '授权与当前机器不匹配（可能因虚机克隆或硬件变更）',
    'invalid_signature': '授权签名无效',
    'invalid_json': '授权文件格式无效',
    'invalid_edition': '授权类型无效，仅支持 trial / official',
    'invalid_expires_at': '授权缺少有效的过期时间',
    'invalid_max_cameras': '授权中的视频路数无效',
    'camera_quota_exceeded': '已达到授权允许的最大视频接入数量',
    'algorithm_not_licensed': '当前授权未包含该算法',
}


# Paths that remain usable without a valid license (login + license import UX).
_LICENSE_EXEMPT_PREFIXES = (
    '/api/login',
    '/api/logout',
    '/api/license/',
    '/api/branding',
)


def _is_license_exempt(path):
    if not path:
        return True
    if path == '/api/health':
        return True
    if path.startswith('/api/license'):
        return True
    for prefix in _LICENSE_EXEMPT_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def register_request_guards(app):
    @app.before_request
    def enforce_license():
        if request.method == 'OPTIONS':
            return None

        path = request.path or ''
        if not path.startswith('/api/'):
            return None

        if _is_license_exempt(path):
            return None

        # Edge agent ingest must still work for ops; business console APIs are gated.
        if path.startswith('/api/edge/') or path.startswith('/api/tasks/edge/'):
            return None

        ok, reason = license_service.ensure_valid()
        if ok:
            return None

        return jsonify({
            'error': REASON_MESSAGES.get(reason, reason or 'license_invalid'),
            'reason': reason,
            'license_required': True,
        }), 403
