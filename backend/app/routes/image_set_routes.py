"""图片测试：上传样本，选中的一张作为一路假视频流。"""
from flask import Blueprint, jsonify, request, send_file, current_app

from app.extensions import db
from app.middleware.auth import role_required, token_required
from app.middleware.license_guard import REASON_MESSAGES
from app.models import Camera
from app.models.camera import DEFAULT_MOUNT_POSITION
import app.services.image_set as image_set_svc
from app.services.image_set import ImageSetError
from app.services.license_service import license_service

image_set_bp = Blueprint('image_set', __name__)

CAMERA_NAME = '图片测试'


def _guard(set_id):
    try:
        image_set_svc.validate_set_id(set_id)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return None


def _find_camera(set_id):
    url = image_set_svc.camera_url(set_id)
    row = Camera.query.filter_by(url=url).order_by(Camera.id.asc()).first()
    return row.to_dict() if row else None


def ensure_image_set_camera(set_id):
    """同一 image-set 地址只建一路视频源。已有则直接返回。"""
    url = image_set_svc.camera_url(set_id)
    existing = Camera.query.filter_by(url=url).order_by(Camera.id.asc()).first()
    if existing:
        return existing.to_dict(), None

    ok, reason = license_service.ensure_valid()
    if not ok:
        return None, REASON_MESSAGES.get(reason, reason or '授权无效')

    current_count = Camera.query.count()
    can_add, quota_reason, status = license_service.can_add_camera(current_count)
    if not can_add:
        max_cameras = status.get('max_cameras', 0)
        msg = REASON_MESSAGES.get(quota_reason, f'授权路数校验失败: {quota_reason}')
        if quota_reason == 'camera_quota_exceeded' and max_cameras:
            msg = f'{msg}（当前 {current_count}/{max_cameras}）'
        return None, f'{msg}。也可在视频源里手工新建，地址填 {url}'

    try:
        camera = Camera(name=CAMERA_NAME, url=url, mount_position=DEFAULT_MOUNT_POSITION)
        db.session.add(camera)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Failed to create image-set camera: {exc}', exc_info=True)
        return None, f'创建视频源失败。也可在视频源里手工新建，地址填 {url}'
    return camera.to_dict(), None


def _with_camera(set_id, payload, create=False):
    if create:
        camera, err = ensure_image_set_camera(set_id)
        payload['camera'] = camera
        payload['camera_error'] = err
    else:
        payload['camera'] = _find_camera(set_id)
    return payload


@image_set_bp.route('/api/image-sets/<set_id>', methods=['GET'])
@token_required
@role_required('vendor')
def get_image_set(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        return jsonify(_with_camera(set_id, image_set_svc.snapshot(set_id)))
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status


@image_set_bp.route('/api/image-sets/<set_id>/images', methods=['POST'])
@token_required
@role_required('vendor')
def upload_images(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    uploads = request.files.getlist('files') or request.files.getlist('file')
    items = []
    for upload in uploads:
        if upload is None:
            continue
        items.append({
            'original': upload.filename or 'image',
            'raw': upload.read(),
        })
    try:
        payload = image_set_svc.add_images(set_id, items)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return jsonify(_with_camera(set_id, payload)), 201


@image_set_bp.route('/api/image-sets/<set_id>/images/<name>', methods=['GET'])
@token_required
@role_required('vendor')
def get_image_file(set_id, name):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        path, mime = image_set_svc.stored_file(set_id, name)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return send_file(path, mimetype=mime, conditional=True, max_age=0)


@image_set_bp.route('/api/image-sets/<set_id>/images/<name>', methods=['PUT'])
@token_required
@role_required('vendor')
def patch_image_label(set_id, name):
    denied = _guard(set_id)
    if denied:
        return denied
    body = request.json or {}
    label = body.get('label') if isinstance(body.get('label'), str) else ''
    try:
        payload = image_set_svc.set_label(set_id, name, label)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return jsonify(_with_camera(set_id, payload))


@image_set_bp.route('/api/image-sets/<set_id>/images/<name>', methods=['DELETE'])
@token_required
@role_required('vendor')
def remove_image(set_id, name):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        payload = image_set_svc.delete_image(set_id, name)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return jsonify(_with_camera(set_id, payload))


@image_set_bp.route('/api/image-sets/<set_id>/current', methods=['POST'])
@token_required
@role_required('vendor')
def select_current(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    body = request.json or {}
    name = body.get('name') if isinstance(body.get('name'), str) else ''
    try:
        payload = image_set_svc.set_current(set_id, name)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return jsonify(_with_camera(set_id, payload, create=True))


@image_set_bp.route('/api/image-sets/<set_id>/camera', methods=['POST'])
@token_required
@role_required('vendor')
def create_camera(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        payload = _with_camera(set_id, image_set_svc.snapshot(set_id), create=True)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if payload.get('camera_error') and not payload.get('camera'):
        return jsonify(payload), 403
    return jsonify(payload)


@image_set_bp.route('/api/edge/image-sets/<set_id>', methods=['GET'])
def edge_image_set_meta(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        return jsonify(image_set_svc.edge_meta(set_id))
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status


@image_set_bp.route('/api/edge/image-sets/<set_id>/current', methods=['GET'])
def edge_current_image(set_id):
    denied = _guard(set_id)
    if denied:
        return denied
    try:
        path, mime = image_set_svc.current_file(set_id)
    except ImageSetError as exc:
        return jsonify({'error': str(exc)}), exc.status
    response = send_file(path, mimetype=mime, conditional=False, max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response
