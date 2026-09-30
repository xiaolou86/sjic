"""
任务管理路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import Task, Algorithm
from app.middleware.auth import token_required
from app.middleware.license_guard import REASON_MESSAGES
from app.utils.calibration import get_calibration_image
from app.services.license_service import license_service

task_bp = Blueprint('task', __name__)


def _is_algorithm_published(algorithm):
    schema = algorithm.parameter_schema or {}
    publish_meta = schema.get('publish_meta', {})
    return bool(publish_meta.get('published', False))


def _blank_id(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _normalize_binding_ids(data):
    for key in ('algorithm_id', 'od_algorithm_id', 'pose_algorithm_id'):
        if key in data:
            data[key] = _blank_id(data[key])


def _check_published_algorithm(algorithm_id, expected_engine=None):
    """返回 (algorithm, error_response)。algorithm_id 为空时两者都是 None。"""
    if not algorithm_id:
        return None, None
    algorithm = Algorithm.query.get(algorithm_id)
    if not algorithm:
        return None, (jsonify({'error': '算法不存在'}), 400)
    if not _is_algorithm_published(algorithm):
        return None, (jsonify({'error': '算法尚未发布，请先在算法管理中发布'}), 400)
    if algorithm.is_system_template():
        return None, (jsonify({
            'error': '不能使用系统模板创建任务，请使用从模板派生并已发布的算法实例',
        }), 400)
    algorithm.ensure_catalog_schema(persist=True)
    from app.utils.algorithm_catalog import engine_needs_model
    engine = algorithm.resolved_engine()
    if expected_engine and engine != expected_engine:
        label = '目标检测' if expected_engine == 'object_detection' else '姿态'
        return None, (jsonify({'error': f'绑定的算法不是{label}算法'}), 400)
    if engine_needs_model(engine) and not algorithm.model_id:
        return None, (jsonify({'error': '算法未绑定模型，请先在算法编辑中绑定模型并发布'}), 400)
    allowed, deny_reason = license_service.is_algorithm_allowed(algorithm.type)
    if not allowed:
        return None, (jsonify({
            'error': REASON_MESSAGES.get(deny_reason, deny_reason or '当前授权不允许使用该算法'),
        }), 403)
    return algorithm, None


def _apply_exam_or_single(data, existing=None):
    """
    混合任务：algorithm_id 为空，od/pose 至少一个。
    单算法任务：沿用 algorithm_id。
    返回 (error_response or None)。
    """
    from app.utils.exam_task import sanitize_exam_params, validate_scene_bindings

    od_id = data.get('od_algorithm_id', getattr(existing, 'od_algorithm_id', None) if existing else None)
    pose_id = data.get('pose_algorithm_id', getattr(existing, 'pose_algorithm_id', None) if existing else None)
    algorithm_id = data.get('algorithm_id', getattr(existing, 'algorithm_id', None) if existing else None)
    if 'od_algorithm_id' in data:
        od_id = data['od_algorithm_id']
    if 'pose_algorithm_id' in data:
        pose_id = data['pose_algorithm_id']
    if 'algorithm_id' in data:
        algorithm_id = data['algorithm_id']

    if od_id or pose_id:
        if algorithm_id:
            return (jsonify({'error': '驾考混合任务不要再绑定单个算法'}), 400)
        _, err = _check_published_algorithm(od_id, 'object_detection')
        if err:
            return err
        _, err = _check_published_algorithm(pose_id, 'pose_behavior')
        if err:
            return err
        params = sanitize_exam_params(data.get('algorithm_parameters') or (existing.algorithm_parameters if existing else {}) or {})
        scene_err = validate_scene_bindings(params, od_id, pose_id)
        if scene_err:
            return (jsonify({'error': scene_err}), 400)
        data['algorithm_id'] = None
        data['od_algorithm_id'] = od_id
        data['pose_algorithm_id'] = pose_id
        data['algorithm_parameters'] = params
        return None

    if not algorithm_id:
        return (jsonify({'error': '请选择要绑定的算法'}), 400)
    algorithm, err = _check_published_algorithm(algorithm_id)
    if err:
        return err
    data['algorithm_id'] = algorithm_id
    data['od_algorithm_id'] = None
    data['pose_algorithm_id'] = None

    params = dict(data.get('algorithm_parameters') or {})
    defaults = (algorithm.parameter_schema or {}).get('default_task_params') or {}
    if defaults and not existing:
        merged = dict(defaults)
        merged.update(params)
        if not params.get('rules') and defaults.get('rules'):
            merged['rules'] = defaults['rules']
        if not params.get('behaviors') and defaults.get('behaviors'):
            merged['behaviors'] = defaults['behaviors']
        data['algorithm_parameters'] = merged
    return None


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
        return jsonify({'error': REASON_MESSAGES.get(reason, reason or '授权无效')}), 403

    data = request.json or {}
    current_app.logger.info(f"Creating new task: {data}")

    # 任务不再接收 modelId，模型由 algorithm.model_id 决定
    data.pop('modelId', None)
    data.pop('algorithm_type', None)
    data.pop('algorithm_engine', None)
    data.pop('algorithm_camera_role', None)
    data.pop('pipeline', None)
    data.pop('warnings', None)
    data.pop('id', None)
    data.pop('created_at', None)
    data.pop('status', None)
    data.pop('run_status', None)
    data.pop('is_scheduled', None)

    # 规范化时段：空串视为未设置
    for key in ('schedule_start', 'schedule_end'):
        if key in data and not str(data.get(key) or '').strip():
            data[key] = None
        elif key in data and data[key] is not None:
            data[key] = str(data[key]).strip()
    if data.get('schedule_start') and data.get('schedule_end'):
        data.setdefault('schedule_paused', False)

    _normalize_binding_ids(data)
    bind_err = _apply_exam_or_single(data)
    if bind_err:
        current_app.logger.warning(f"Create task rejected: {bind_err[0].get_json()}")
        return bind_err

    try:
        task = Task(**data)
        task.save_calibration_image()
        db.session.add(task)
        db.session.commit()
        current_app.logger.info(f"Task created successfully: id={task.id} name={task.name}")
        body = task.to_dict()
        from app.utils.exam_task import camera_pipeline_warnings
        warnings = camera_pipeline_warnings(task.cameraId, exclude_task_id=task.id)
        if warnings:
            body['warnings'] = warnings
        return jsonify(body), 201
    except Exception as e:
        current_app.logger.error(f"Error creating task: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': REASON_MESSAGES.get(reason, reason or '授权无效')}), 403

      data = request.json or {}
      # 任务更新忽略 modelId，模型由算法绑定决定
      data.pop('modelId', None)
      data.pop('is_scheduled', None)
      data.pop('algorithm_type', None)
      data.pop('algorithm_engine', None)
      data.pop('pipeline', None)
      data.pop('warnings', None)
      data.pop('created_at', None)
      data.pop('id', None)

      for key in ('schedule_start', 'schedule_end'):
        if key in data and not str(data.get(key) or '').strip():
          data[key] = None
        elif key in data and data[key] is not None:
          data[key] = str(data[key]).strip()

      task = Task.query.get_or_404(task_id)

      _normalize_binding_ids(data)
      bind_err = _apply_exam_or_single(data, existing=task)
      if bind_err:
        return bind_err

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
