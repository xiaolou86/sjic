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
    """
    启动检测任务
    ---
    tags:
      - 任务控制 (Detection)
    summary: 下发边缘计算任务
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - task_id
          properties:
            task_id:
              type: integer
              description: 要下发启动的任务 ID
    responses:
      200:
        description: 指令已通过 MQTT 成功下发给边缘盒子
      400:
        description: 任务不存在或下发失败
    """
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
    """
    停止检测任务
    ---
    tags:
      - 任务控制 (Detection)
    summary: 停止执行指定的检测任务
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - task_id
          properties:
            task_id:
              type: integer
    responses:
      200:
        description: 停止命令下发成功
      400:
        description: 停止失败
    """
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
