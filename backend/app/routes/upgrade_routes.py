"""页面上传安装包，并触发平台本机升级或边缘节点升级。"""
from flask import Blueprint, jsonify, request, current_app

from app.middleware.auth import token_required, role_required, get_token_payload
from app.models.edge_node import EdgeNode
from app.extensions import db
from app.services.mqtt_service import mqtt_service
from app.services.upgrade_service import (
    UpgradeError,
    package_meta,
    platform_status,
    request_platform_upgrade,
    stage_package,
    upgrade_download_path,
)
from app.utils.release_pkg import read_version

upgrade_bp = Blueprint('upgrade', __name__)


def _operator():
    payload = get_token_payload() or {}
    return payload.get('user'), payload.get('role')


@upgrade_bp.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'version': read_version()})


@upgrade_bp.route('/api/admin/upgrades', methods=['GET'])
@token_required
@role_required('customer', 'vendor')
def get_upgrades():
    try:
        return jsonify(platform_status())
    except UpgradeError as exc:
        return jsonify({'error': str(exc)}), 400


@upgrade_bp.route('/api/admin/upgrades/<component>', methods=['POST'])
@token_required
@role_required('customer', 'vendor')
def upload_upgrade(component):
    if component not in ('platform', 'edge'):
        return jsonify({'error': '未知安装包类型'}), 404
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return jsonify({'error': '请选择安装包'}), 400
    user, role = _operator()
    current_app.logger.warning('Upgrade package upload component=%s user=%s role=%s', component, user, role)
    try:
        meta = stage_package(component, upload)
    except UpgradeError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({
        'message': '安装包已校验',
        'component': component,
        'version': meta['version'],
    })


@upgrade_bp.route('/api/admin/upgrades/platform/apply', methods=['POST'])
@token_required
@role_required('customer', 'vendor')
def apply_platform_upgrade():
    user, role = _operator()
    current_app.logger.warning('Platform upgrade requested user=%s role=%s', user, role)
    try:
        meta = request_platform_upgrade()
    except UpgradeError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({
        'message': f'已提交升级到 {meta["version"]}，平台会短暂中断后自动恢复',
        'version': meta['version'],
    })


@upgrade_bp.route('/api/nodes/<int:node_id>/upgrade', methods=['POST'])
@token_required
@role_required('customer', 'vendor')
def upgrade_edge_node(node_id):
    node = EdgeNode.query.get(node_id)
    if not node:
        return jsonify({'error': 'Node not found'}), 404
    meta = None
    try:
        meta = package_meta('edge')
    except UpgradeError as exc:
        return jsonify({'error': str(exc)}), 400
    if not meta:
        return jsonify({'error': '请先在系统设置中上传边缘安装包'}), 400

    user, role = _operator()
    current_app.logger.warning(
        'Edge upgrade requested node_id=%s mac=%s version=%s user=%s role=%s',
        node.id, node.mac_address, meta.get('version'), user, role,
    )
    node.upgrade_status = 'queued'
    node.upgrade_target_version = meta['version']
    node.upgrade_message = '已下发'
    db.session.commit()
    try:
        mqtt_service.publish_agent_upgrade(node.mac_address, {
            'version': meta['version'],
            'min_version': meta.get('min_version') or '1.0.0',
            'sha256': meta['sha256'],
            'url': upgrade_download_path(meta['filename']),
        })
    except Exception as exc:
        node.upgrade_status = 'failed'
        node.upgrade_message = '下发失败'
        db.session.commit()
        current_app.logger.error('Failed to publish agent upgrade: %s', exc)
        return jsonify({'error': f'下发升级指令失败: {exc}'}), 500
    return jsonify({
        'message': f'已通知 {node.name} 升级到 {meta["version"]}',
        'node_id': node.id,
        'version': meta['version'],
    })
