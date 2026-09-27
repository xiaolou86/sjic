"""驾考混合任务：一个任务最多绑定一路目标检测和一路姿态。"""


def _enabled(items):
    return [
        item for item in (items or [])
        if isinstance(item, dict) and item.get('enabled', True) is not False
    ]


def scene_needs(params):
    """按已启用场景决定这一帧要跑哪些模型。"""
    params = params or {}
    rules = _enabled(params.get('rules'))
    behaviors = _enabled([
        item for item in (params.get('behaviors') or [])
        if isinstance(item, dict) and item.get('type') != 'smart_glasses'
    ])
    fusions = _enabled(params.get('fusions'))
    return {
        'rules': rules,
        'behaviors': behaviors,
        'fusions': fusions,
        'need_od': bool(rules or fusions),
        'need_pose': bool(behaviors or fusions),
    }


def sanitize_exam_params(params):
    """混合任务里的智能眼镜只放在 fusions，避免再走纯姿态逻辑。"""
    params = dict(params or {})
    params['behaviors'] = [
        item for item in (params.get('behaviors') or [])
        if not (isinstance(item, dict) and item.get('type') == 'smart_glasses')
    ]
    if not isinstance(params.get('rules'), list):
        params['rules'] = []
    if not isinstance(params.get('fusions'), list):
        params['fusions'] = []
    return params


def validate_scene_bindings(params, od_id, pose_id):
    """场景和绑定不一致时返回错误文案。"""
    params = params or {}
    rules = [item for item in (params.get('rules') or []) if isinstance(item, dict)]
    behaviors = [
        item for item in (params.get('behaviors') or [])
        if isinstance(item, dict) and item.get('type') != 'smart_glasses'
    ]
    fusions = [item for item in (params.get('fusions') or []) if isinstance(item, dict)]
    if rules and not od_id:
        return '添加了检测场景，需要绑定目标检测算法'
    if behaviors and not pose_id:
        return '添加了姿态场景，需要绑定姿态算法'
    if fusions and not (od_id and pose_id):
        return '智能眼镜需要同时绑定目标检测算法和姿态算法'
    for fusion in _enabled(fusions):
        class_ids = fusion.get('class_ids') or []
        if not class_ids:
            return '智能眼镜场景需要选择眼镜类别'
    return None


def camera_pipeline_warnings(camera_id, exclude_task_id=None):
    """同一摄像头上已有检测/姿态任务时提示，避免两路拉流。不阻止保存。"""
    if not camera_id:
        return []
    from app.models import Algorithm, Task

    warnings = []
    try:
        camera_id = int(camera_id)
    except (TypeError, ValueError):
        return []
    for other in Task.query.filter_by(cameraId=camera_id).all():
        if exclude_task_id and other.id == exclude_task_id:
            continue
        engines = set()
        if other.od_algorithm_id:
            engines.add('object_detection')
        if other.pose_algorithm_id:
            engines.add('pose_behavior')
        if other.algorithm_id:
            algo = Algorithm.query.get(other.algorithm_id)
            if algo and algo.resolved_engine() in ('object_detection', 'pose_behavior'):
                engines.add(algo.resolved_engine())
        if engines:
            warnings.append(
                f'该摄像头已有任务「{other.name}」在使用目标检测或姿态，同时运行会各拉一路视频'
            )
    return warnings
