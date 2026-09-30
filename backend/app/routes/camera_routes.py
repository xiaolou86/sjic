"""
摄像头管理路由蓝图
"""
from flask import Blueprint, jsonify, request, Response, current_app
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db
from app.models import Alert, Camera, Task, EdgeNode
from app.models.camera import MOUNT_POSITIONS, DEFAULT_MOUNT_POSITION
from app.middleware.auth import token_required
from app.services.mqtt_service import mqtt_service
from app.services.license_service import license_service
from app.utils.db_compat import ensure_alert_camera_optional
import cv2

camera_bp = Blueprint('camera', __name__)


def _unbind_camera_from_nodes(camera_id):
    for node in EdgeNode.query.all():
        if not isinstance(node.bound_cameras, list):
            continue
        kept = []
        removed = False
        for raw in node.bound_cameras:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value == camera_id:
                removed = True
                continue
            kept.append(value)
        if removed:
            node.bound_cameras = kept
            flag_modified(node, 'bound_cameras')


@camera_bp.route('/api/cameras', methods=['GET'])
@token_required
def get_cameras():
    """
    获取所有摄像头
    ---
    tags:
      - 摄像头管理 (Cameras)
    summary: 获取摄像头列表
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: 摄像头列表
    """
    try:
        cameras = Camera.query.all()
        current_app.logger.info([camera.to_dict() for camera in cameras])
        return jsonify([camera.to_dict() for camera in cameras])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@camera_bp.route('/api/cameras', methods=['POST'])
@token_required
def create_camera():
    """
    创建新摄像头
    ---
    tags:
      - 摄像头管理 (Cameras)
    summary: 注册新摄像头
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            url:
              type: string
              description: RTSP/HTTP流地址
            mount_position:
              type: string
              description: 安装位置 front_top/back_top/side_top/top
    responses:
      201:
        description: 摄像头创建成功
    """
    try:
        ok, reason = license_service.ensure_valid()
        if not ok:
            return jsonify({'error': f'License invalid: {reason}'}), 403

        data = request.json or {}
        current_app.logger.info(f"Creating new camera: {data}")

        if not data.get('name') or not data.get('url'):
            return jsonify({'error': 'Name and URL are required'}), 400

        current_count = Camera.query.count()
        can_add, quota_reason, status = license_service.can_add_camera(current_count)
        if not can_add:
            from app.middleware.license_guard import REASON_MESSAGES
            max_cameras = status.get('max_cameras', 0)
            msg = REASON_MESSAGES.get(quota_reason, f'授权路数校验失败: {quota_reason}')
            if quota_reason == 'camera_quota_exceeded' and max_cameras:
                msg = f'{msg}（当前 {current_count}/{max_cameras}）'
            return jsonify({
                'error': msg,
                'reason': quota_reason,
                'max_cameras': max_cameras,
                'current_cameras': current_count
            }), 403

        mount_position = data.get('mount_position') or DEFAULT_MOUNT_POSITION
        if mount_position not in MOUNT_POSITIONS:
            return jsonify({
                'error': f'无效的摄像头位置: {mount_position}，可选 {", ".join(MOUNT_POSITIONS)}'
            }), 400

        camera = Camera(
            name=data['name'],
            url=data['url'],
            mount_position=mount_position,
        )
        db.session.add(camera)
        db.session.commit()

        current_app.logger.info(f"Camera created successfully: id={camera.id}")
        return jsonify(camera.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to create camera: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@camera_bp.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
@token_required
def delete_camera(camera_id):
    """
    删除摄像头
    ---
    tags:
      - 摄像头管理 (Cameras)
    summary: 删除指定摄像头
    security:
      - APIKeyHeader: []
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: 删除成功
    """
    ensure_alert_camera_optional()
    camera = Camera.query.get_or_404(camera_id)
    related_tasks = Task.query.filter_by(cameraId=camera_id).all()
    task_ids = {task.id for task in related_tasks}
    camera_name = camera.name

    try:
        # 保留告警和图片，只解开外键。名称先记下来，页面上仍能看出是哪一路。
        alerts = Alert.query.filter(Alert.camera_id == camera_id).all()
        if task_ids:
            linked = Alert.query.filter(Alert.task_id.in_(task_ids)).all()
            known = {alert.id for alert in alerts}
            alerts.extend(alert for alert in linked if alert.id not in known)
        for alert in alerts:
            if not (alert.camera_name or '').strip():
                alert.camera_name = camera_name
            if alert.task_id in task_ids:
                alert.task_id = None
        db.session.flush()

        for task in related_tasks:
            if task.edge_node_id:
                edge_node = EdgeNode.query.get(task.edge_node_id)
                if edge_node:
                    mqtt_service.publish_task_stop(edge_node.mac_address, task.id)
            db.session.delete(task)

        _unbind_camera_from_nodes(camera_id)
        db.session.delete(camera)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to delete camera {camera_id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

    return '', 204


@camera_bp.route('/api/cameras/<int:camera_id>', methods=['PUT'])
@token_required
def update_camera(camera_id):
    """
    更新摄像头
    ---
    tags:
      - 摄像头管理 (Cameras)
    summary: 修改指定摄像头的名称和地址
    security:
      - APIKeyHeader: []
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            url:
              type: string
    responses:
      200:
        description: 更新成功
    """
    try:
        camera = Camera.query.get_or_404(camera_id)
        data = request.json or {}

        if 'name' in data:
            camera.name = data['name']
        if 'url' in data:
            camera.url = data['url']
        if 'mount_position' in data:
            mount_position = data.get('mount_position') or DEFAULT_MOUNT_POSITION
            if mount_position not in MOUNT_POSITIONS:
                return jsonify({
                    'error': f'无效的摄像头位置: {mount_position}，可选 {", ".join(MOUNT_POSITIONS)}'
                }), 400
            camera.mount_position = mount_position

        db.session.commit()
        current_app.logger.info(f"Camera updated successfully: id={camera.id}")
        return jsonify(camera.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update camera {camera_id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@camera_bp.route('/api/cameras/capture', methods=['POST'])
def capture_frame():
    """
    获取摄像头当前帧
    ---
    tags:
      - 摄像头管理 (Cameras)
    summary: 实时截取摄像头图像
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            camera_id:
              type: integer
    responses:
      200:
        description: 返回 JPEG 图像二进制流
    """
    try:
        data = request.json
        camera_id = data.get('camera_id')

        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        cap = cv2.VideoCapture(camera.get_rtsp_url())

        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera: {camera_id}")

        # 读取一帧
        ret, frame = cap.read()
        cap.release()

        if not ret:
            raise RuntimeError("Failed to capture frame")

        # 将图片编码为JPEG
        _, buffer = cv2.imencode('.jpg', frame)

        # 确保返回正确的 MIME 类型和二进制数据
        return Response(
            buffer.tobytes(),
            mimetype='image/jpeg',
            headers={
                'Content-Type': 'image/jpeg',
                'Content-Disposition': 'inline'
            }
        )
    except Exception as e:
        current_app.logger.error(f"Capture frame error: {str(e)}")
        return jsonify({'error': str(e)}), 500
