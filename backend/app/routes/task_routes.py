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
    """获取算法设置"""
    tasks = Task.query.all()
    return jsonify([task.to_dict() for task in tasks])


@task_bp.route('/api/tasks', methods=['POST'])
@token_required
def create_tasks():
    """创建算法设置"""
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
    """更新算法设置"""
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
    """删除算法设置"""
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return '', 204


@task_bp.route('/api/tasks/<int:task_id>/detail', methods=['GET'])
@token_required
def get_task_detail(task_id):
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
