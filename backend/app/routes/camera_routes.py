"""
摄像头管理路由蓝图
"""
from flask import Blueprint, jsonify, request, Response, current_app
from app.extensions import db
from app.models import Camera
from app.middleware.auth import token_required
import cv2

camera_bp = Blueprint('camera', __name__)


@camera_bp.route('/api/cameras', methods=['GET'])
@token_required
def get_cameras():
    """获取所有摄像头"""
    try:
        cameras = Camera.query.all()
        current_app.logger.info([camera.to_dict() for camera in cameras])
        return jsonify([camera.to_dict() for camera in cameras])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@camera_bp.route('/api/cameras', methods=['POST'])
@token_required
def create_camera():
    """创建新摄像头"""
    try:
        data = request.json
        current_app.logger.info(f"Creating new camera: {data}")

        camera = Camera(
            name=data['name'],
            url=data['url']
        )
        db.session.add(camera)
        db.session.commit()

        current_app.logger.info(f"Camera created successfully: id={camera.id}")
        return jsonify(camera.to_dict()), 201
    except Exception as e:
        current_app.logger.error(f"Failed to create camera: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@camera_bp.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
@token_required
def delete_camera(camera_id):
    """删除摄像头"""
    camera = Camera.query.get_or_404(camera_id)
    db.session.delete(camera)
    db.session.commit()
    return '', 204


@camera_bp.route('/api/cameras/capture', methods=['POST'])
def capture_frame():
    """获取摄像头当前帧"""
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
