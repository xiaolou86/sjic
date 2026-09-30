"""Record important console operations (create / update / delete / login / logout)."""
import re
from flask import request, current_app
from sqlalchemy.orm import Session

from app.extensions import db
from app.middleware.auth import get_token_payload
from app.models.operation_log import OperationLog


_SKIP_PREFIXES = (
    '/api/analytics/',
    '/api/edge/',
    '/api/stream',
    '/api/hls/',
    '/api/mjpeg/',
    '/api/cameras/capture',
    '/api/logs',
)

_POWER_LABELS = {
    'reboot': '重启',
    'shutdown': '关机',
    'wake': '唤醒',
}

_REVIEW_LABELS = {
    'confirmed': '确认为属实',
    'false_positive': '标记为误报',
    'pending': '重置为待确认',
}

OPERATION_MODULES = (
    '认证', '视频源', '任务', '算法', '模型', '节点', '告警',
    '检测', '训练', '授权', '系统设置', '系统',
)
# 与导航菜单一致：普通管理员（customer）看不到厂商专属模块。
CUSTOMER_HIDDEN_MODULES = frozenset({'模型', '训练'})
SUPER_ADMIN_USERNAME = 'super_admin'


def modules_for_role(role):
    if role == 'vendor':
        return list(OPERATION_MODULES)
    return [name for name in OPERATION_MODULES if name not in CUSTOMER_HIDDEN_MODULES]


def operation_visible_to(viewer_role, log_username, log_role, log_module):
    """普通管理员不能看 super_admin 的操作/登录，也不能看无权限模块。"""
    if viewer_role == 'vendor':
        return True
    if (log_username or '').strip() == SUPER_ADMIN_USERNAME:
        return False
    if (log_role or '') == 'vendor':
        return False
    if log_module in CUSTOMER_HIDDEN_MODULES:
        return False
    return True


def _name(body):
    if not isinstance(body, dict):
        return ''
    for key in ('name', 'product_name'):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return ''


def describe_operation(method, path, body):
    """Return action/module/summary for a mutating request, or None to skip."""
    method = (method or '').upper()
    path = path or ''
    if method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return None

    body = body if isinstance(body, dict) else {}
    name = _name(body)

    if path == '/api/login' and method == 'POST':
        username = body.get('username') if isinstance(body.get('username'), str) else ''
        who = username.strip()[:64] or '未知用户'
        return {'action': 'login', 'module': '认证', 'summary': f'登录：{who}', 'username': who}

    if path == '/api/logout' and method == 'POST':
        return {'action': 'logout', 'module': '认证', 'summary': '退出登录'}

    if path == '/api/auth/password' and method == 'POST':
        return {'action': 'update', 'module': '认证', 'summary': '修改登录密码'}

    rules = (
        ('POST', r'^/api/cameras$', 'create', '视频源', f'创建视频源 {name}'.strip()),
        ('PUT', r'^/api/cameras/(\d+)$', 'update', '视频源', f'修改视频源 {name or "#"}'),
        ('DELETE', r'^/api/cameras/(\d+)$', 'delete', '视频源', '删除视频源'),
        ('POST', r'^/api/tasks$', 'create', '任务', f'创建任务 {name}'.strip()),
        ('PUT', r'^/api/tasks/(\d+)$', 'update', '任务', f'修改任务 {name or "#"}'),
        ('DELETE', r'^/api/tasks/(\d+)$', 'delete', '任务', '删除任务'),
        ('POST', r'^/api/algorithms$', 'create', '算法', f'创建算法 {name}'.strip()),
        ('POST', r'^/api/algorithms/(\d+)/derive$', 'create', '算法', f'派生算法 {name}'.strip()),
        ('PUT', r'^/api/algorithms/(\d+)$', 'update', '算法', f'修改算法 {name or "#"}'),
        ('DELETE', r'^/api/algorithms/(\d+)$', 'delete', '算法', '删除算法'),
        ('POST', r'^/api/algorithms/(\d+)/publish$', 'update', '算法', '发布算法'),
        ('POST', r'^/api/models/upload$', 'create', '模型', f'上传模型 {name}'.strip()),
        ('PUT', r'^/api/models/(\d+)$', 'update', '模型', f'修改模型 {name or "#"}'),
        ('DELETE', r'^/api/models/(\d+)$', 'delete', '模型', '删除模型'),
        ('POST', r'^/api/settings$', 'update', '系统设置', '保存系统设置'),
        ('POST', r'^/api/settings/logo$', 'update', '系统设置', '上传 Logo'),
        ('DELETE', r'^/api/settings/logo$', 'delete', '系统设置', '删除 Logo'),
        ('POST', r'^/api/license/import$', 'update', '授权', '导入授权文件'),
        ('POST', r'^/api/alerts$', 'create', '告警', '创建告警'),
        ('DELETE', r'^/api/alerts/(\d+)$', 'delete', '告警', '删除告警'),
        ('PUT', r'^/api/nodes/(\d+)$', 'update', '节点', f'修改节点 {name or "#"}'),
        ('DELETE', r'^/api/nodes/(\d+)$', 'delete', '节点', '删除节点'),
        ('POST', r'^/api/nodes/(\d+)/restart$', 'operate', '节点', '重启节点'),
        ('POST', r'^/api/admin/restart-backend$', 'operate', '系统', '重启后端'),
        ('POST', r'^/api/admin/upgrades/platform$', 'update', '系统', '上传平台安装包'),
        ('POST', r'^/api/admin/upgrades/edge$', 'update', '系统', '上传边缘安装包'),
        ('POST', r'^/api/admin/upgrades/platform/apply$', 'operate', '系统', '升级管理平台'),
        ('POST', r'^/api/nodes/(\d+)/upgrade$', 'operate', '节点', '升级节点'),
        ('POST', r'^/api/detection/start$', 'operate', '检测', '启动检测'),
        ('POST', r'^/api/detection/stop$', 'operate', '检测', '停止检测'),
        ('POST', r'^/api/training/start$', 'operate', '训练', '启动模型训练'),
    )

    for rule_method, pattern, action, module, summary in rules:
        if method != rule_method:
            continue
        matched = re.match(pattern, path)
        if not matched:
            continue
        target_id = matched.group(1) if matched.groups() else ''
        text = summary.replace('#', f'#{target_id}' if target_id else '')
        if target_id and action in ('update', 'delete', 'operate', 'create') and '#' not in text and name == '':
            text = f'{text} #{target_id}'
        return {'action': action, 'module': module, 'summary': text[:255]}

    review = re.match(r'^/api/alerts/(\d+)/review$', path)
    if review and method in ('POST', 'PATCH'):
        status = body.get('review_status') if isinstance(body.get('review_status'), str) else ''
        verb = _REVIEW_LABELS.get(status, '审核告警')
        return {'action': 'update', 'module': '告警', 'summary': f'{verb} #{review.group(1)}'}

    power = re.match(r'^/api/nodes/(\d+)/power$', path)
    if power and method == 'POST':
        action_name = body.get('action') if isinstance(body.get('action'), str) else ''
        verb = _POWER_LABELS.get(action_name, '电源操作')
        return {'action': 'operate', 'module': '节点', 'summary': f'{verb}节点 #{power.group(1)}'}

    return None


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()[:64]
    return (request.remote_addr or '')[:64]


def _safe_json():
    if request.content_type and 'multipart/form-data' in request.content_type:
        allowed = ('name', 'product_name', 'action', 'review_status', 'username')
        return {key: request.form.get(key) for key in allowed if request.form.get(key)}
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def write_operation_log(**fields):
    try:
        with Session(db.engine) as session:
            session.add(OperationLog(**fields))
            session.commit()
    except Exception:
        current_app.logger.exception('Failed to write operation log')


def record_request(response):
    spec = describe_operation(request.method, request.path, _safe_json())
    if not spec:
        return

    payload = get_token_payload() or {}
    username = spec.pop('username', None) or payload.get('user') or ''
    success = 200 <= response.status_code < 400
    if spec['action'] == 'login' and not success:
        spec['summary'] = spec['summary'].replace('登录：', '登录失败：', 1)

    write_operation_log(
        username=(username or '')[:64],
        role=(payload.get('role') or '')[:20],
        action=spec['action'],
        module=spec['module'],
        summary=spec['summary'][:255],
        success=success,
        status_code=response.status_code,
        ip=_client_ip(),
    )


def register_audit(app):
    @app.after_request
    def _audit_after_request(response):
        try:
            record_request(response)
        except Exception:
            app.logger.exception('Audit hook failed')
        return response
