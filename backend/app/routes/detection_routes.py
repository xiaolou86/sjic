"""
检测任务路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.middleware.auth import token_required
from app.services.detector import DetectorService

detection_bp = Blueprint('detection', __name__)

# 初始化服务
detector_service = DetectorService()


@detection_bp.route('/api/detection/start', methods=['POST'])
@token_required
def start_detection():
    """启动检测任务"""
    try:
        data = request.json
        task_id = data.get('task_id')

        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400

        result = detector_service.start_detection(task_id)

        if result['success']:
            return jsonify({'message': result['message']}), 200
        else:
            return jsonify({'error': result['message']}), 400

    except Exception as e:
        current_app.logger.error(f"Error starting detection: {str(e)}")
        return jsonify({'error': str(e)}), 500


@detection_bp.route('/api/detection/stop', methods=['POST'])
@token_required
def stop_detection():
    """停止检测任务"""
    try:
        data = request.json
        task_id = data.get('task_id')

        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400

        result = detector_service.stop_detection(task_id)

        if result['success']:
            return jsonify({'message': result['message']}), 200
        else:
            return jsonify({'error': result['message']}), 400

    except Exception as e:
        current_app.logger.error(f"Error stopping detection: {str(e)}")
        return jsonify({'error': str(e)}), 500
