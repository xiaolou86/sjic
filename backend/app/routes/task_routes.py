"""
任务管理路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import Task
from app.middleware.auth import token_required
from app.utils.calibration import get_calibration_image

task_bp = Blueprint('task', __name__)


@task_bp.route('/api/tasks', methods=['GET'])
@token_required
def get_tasks():
    """
    获取所有检测任务
    ---
    tags:
      - 任务管理 (Tasks)
    summary: 获取全量任务列表
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: 返回检测任务表
    """
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
    data = request.json
    current_app.logger.info(f"Creating new task: {data}")
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
        data = request.json
        task = Task.query.get_or_404(task_id)

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
