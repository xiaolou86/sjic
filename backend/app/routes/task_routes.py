"""
任务管理路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import Task, Algorithm
from app.middleware.auth import token_required
from app.utils.calibration import get_calibration_image
from app.services.license_service import license_service

task_bp = Blueprint('task', __name__)


@task_bp.route('/api/tasks/edge/<mac_address>', methods=['GET'])
def get_edge_tasks(mac_address):
    """
    边缘设备启动时查询分配给自己的有效任务。
    面向边缘端提供，免去 @token_required 校验。
    """
    from app.models import EdgeNode
    node = EdgeNode.query.filter_by(mac_address=mac_address).first()
    if not node:
        return jsonify({"success": False, "error": "Node not found"}), 404
        
    tasks = Task.query.filter_by(edge_node_id=node.id).all()
    task_ids = [str(t.id) for t in tasks]
    return jsonify({"success": True, "valid_task_ids": task_ids}), 200


@task_bp.route('/api/tasks', methods=['GET'])
@token_required
def get_tasks():
    """
    获取所有检测任务 (供前端控制台使用)
    """
    # 也可以加上 query param 支持给前端过滤
    mac_address = request.args.get('mac_address')
    if mac_address:
        from app.models import EdgeNode
        node = EdgeNode.query.filter_by(mac_address=mac_address).first()
        if node:
            tasks = Task.query.filter_by(edge_node_id=node.id).all()
        else:
            tasks = []
    else:
        tasks = Task.query.all()
        
    return jsonify([task.to_dict() for task in tasks])


@task_bp.route('/api/tasks', methods=['POST'])
@token_required
def create_tasks():
    """
    创建检测任务
    ---
    tags:
      - 任务管理 (Tasks)
    summary: 新增算法与监控摄像头的绑定任务
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
    responses:
      201:
        description: 任务创建成功
    """
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    data = request.json or {}
    current_app.logger.info(f"Creating new task: {data}")

    # 任务不再接收 modelId，模型由 algorithm.model_id 决定
    data.pop('modelId', None)

    algorithm_id = data.get('algorithm_id')
    if not algorithm_id:
        return jsonify({'error': 'algorithm_id is required'}), 400

    algorithm = Algorithm.query.get(algorithm_id)
    if not algorithm:
        return jsonify({'error': 'Algorithm not found'}), 400
    if not algorithm.model_id:
        return jsonify({'error': 'Algorithm has no published model. Please publish algorithm version first.'}), 400

    allowed, deny_reason = license_service.is_algorithm_allowed(algorithm.type)
    if not allowed:
        return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

    task = Task(**data)
    task.save_calibration_image()
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201


@task_bp.route('/api/tasks/<int:task_id>', methods=['PUT'])
@token_required
def update_tasks(task_id):
    """
    更新检测任务参数
    ---
    tags:
      - 任务管理 (Tasks)
    summary: 更新任务（支持 AI 标注画框与置信度等）
    security:
      - APIKeyHeader: []
    parameters:
      - name: task_id
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: 任务更新成功
    """
    try:
        ok, reason = license_service.ensure_valid()
        if not ok:
            return jsonify({'error': f'License invalid: {reason}'}), 403

        data = request.json or {}
        # 任务更新忽略 modelId，模型由算法绑定决定
        data.pop('modelId', None)

        task = Task.query.get_or_404(task_id)

        next_algorithm_id = data.get('algorithm_id', task.algorithm_id)
        if next_algorithm_id:
            algorithm = Algorithm.query.get(next_algorithm_id)
            if not algorithm:
                return jsonify({'error': 'Algorithm not found'}), 400
            if not algorithm.model_id:
                return jsonify({'error': 'Algorithm has no published model. Please publish algorithm version first.'}), 400
            allowed, deny_reason = license_service.is_algorithm_allowed(algorithm.type)
            if not allowed:
                return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

        for key, value in data.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.save_calibration_image()
        db.session.add(task)  # 确保对象被跟踪
        db.session.commit()

        current_app.logger.info(f"Task updated successfully: {task.to_dict()}")
        return jsonify(task.to_dict())

    except Exception as e:
        current_app.logger.error(f"Error updating task: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@task_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@token_required
def delete_tasks(task_id):
    """
    删除任务
    ---
    tags:
      - 任务管理 (Tasks)
    summary: 删除关联任务 (但不停止进程)
    security:
      - APIKeyHeader: []
    parameters:
      - name: task_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: 删除成功
    """
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return '', 204


@task_bp.route('/api/tasks/<int:task_id>/detail', methods=['GET'])
@token_required
def get_task_detail(task_id):
    """
    获取任务具体标定与参数
    ---
    tags:
      - 任务管理 (Tasks)
    summary: 获取任务细节
    security:
      - APIKeyHeader: []
    parameters:
      - name: task_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 带有图像的标定信息
    """
    task = Task.query.get_or_404(task_id)

    # 获取任务详情，包括标定图像
    task_data = task.to_dict()

    # 如果有标定图像，添加图像数据
    if task.algorithm_parameters and 'calibration' in task.algorithm_parameters:
        calibration = task.algorithm_parameters['calibration']
        if 'image_path' in calibration:
            # 获取图像数据
            image_data = get_calibration_image(task_id)
            if image_data:
                calibration['image_data'] = image_data

    return jsonify(task_data)
