"""混合任务：一个任务最多绑定一路目标检测和一路姿态。"""

# 这些类型只出现在 fusions，不能再当作纯姿态行为。
_FUSION_ONLY_TYPES = frozenset({'smart_glasses', 'smart_watch'})
# 已下线的姿态行为，保存任务时从 behaviors 里去掉。
_DROPPED_POSE_TYPES = frozenset({'chin_rest'})

_FUSION_BIND_ERRORS = {
    'smart_glasses': '智能眼镜需要同时绑定目标检测算法和姿态算法',
    'smart_watch': '智能手表需要同时绑定目标检测算法和姿态算法',
}

_FUSION_CLASS_ERRORS = {
    'smart_glasses': '智能眼镜场景需要选择眼镜类别',
    'smart_watch': '智能手表场景需要选择手表类别',
}


def _enabled(items):
    return [
        item for item in (items or [])
        if isinstance(item, dict) and item.get('enabled', True) is not False
    ]


def _is_dropped_pose(item):
    return (
        item.get('type') in _DROPPED_POSE_TYPES
        or item.get('scene_preset_id') in _DROPPED_POSE_TYPES
        or item.get('alert_type') in _DROPPED_POSE_TYPES
    )


def _pose_behaviors(items):
    return [
        item for item in (items or [])
        if isinstance(item, dict)
        and item.get('type') not in _FUSION_ONLY_TYPES
        and not _is_dropped_pose(item)
    ]


def scene_needs(params):
    """按已启用场景决定这一帧要跑哪些模型。"""
    params = params or {}
    rules = _enabled(params.get('rules'))
    behaviors = _enabled(_pose_behaviors(params.get('behaviors')))
    fusions = _enabled(params.get('fusions'))
    return {
        'rules': rules,
        'behaviors': behaviors,
        'fusions': fusions,
        'need_od': bool(rules or fusions),
        'need_pose': bool(behaviors or fusions),
    }


def strip_dropped_pose_behaviors(params):
    """去掉已下线的姿态行为，保留其余参数。"""
    params = dict(params or {})
    if isinstance(params.get('behaviors'), list):
        params['behaviors'] = _pose_behaviors(params.get('behaviors'))
    return params


def sanitize_exam_params(params):
    """融合场景只放在 fusions，避免再走纯姿态逻辑。"""
    params = strip_dropped_pose_behaviors(params)
    if not isinstance(params.get('behaviors'), list):
        params['behaviors'] = []
    if not isinstance(params.get('rules'), list):
        params['rules'] = []
    if not isinstance(params.get('fusions'), list):
        params['fusions'] = []
    return params


def _chosen_class_ids(item):
    raw = item.get('class_ids') if isinstance(item, dict) else None
    if not isinstance(raw, (list, tuple)):
        return []
    ids = []
    for value in raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _is_camera_occlusion(rule):
    return (
        rule.get('type') == 'camera_occlusion'
        or rule.get('scene_preset_id') == 'camera_occlusion'
    )


def missing_detection_class(rules):
    """已启用的目标检测场景必须显式选择类别。摄像头遮挡不看类别。"""
    for rule in _enabled(rules):
        if _is_camera_occlusion(rule) or _chosen_class_ids(rule):
            continue
        name = rule.get('name') or '检测场景'
        return f'检测场景「{name}」需要选择类别'
    return None


def _allowlist(allowed_ids):
    allowed = set()
    for value in allowed_ids or []:
        try:
            allowed.add(int(value))
        except (TypeError, ValueError):
            continue
    return allowed


def classes_outside_allowlist(items, allowed_ids):
    """算法勾选了部分类别时，场景只能使用这些类别。未勾选则不限制。"""
    allowed = _allowlist(allowed_ids)
    if not allowed:
        return None
    for item in _enabled(items):
        outside = [class_id for class_id in _chosen_class_ids(item) if class_id not in allowed]
        if outside:
            name = item.get('name') or '场景'
            return f'场景「{name}」只能选择算法已勾选的类别'
    return None


def validate_scene_bindings(params, od_id, pose_id, allowed_class_ids=None):
    """场景和绑定不一致时返回错误文案。"""
    params = params or {}
    rules = [item for item in (params.get('rules') or []) if isinstance(item, dict)]
    behaviors = _pose_behaviors(params.get('behaviors'))
    fusions = [item for item in (params.get('fusions') or []) if isinstance(item, dict)]
    if rules and not od_id:
        return '添加了检测场景，需要绑定目标检测算法'
    if behaviors and not pose_id:
        return '添加了姿态场景，需要绑定姿态算法'
    if fusions and not (od_id and pose_id):
        types = {item.get('type') for item in fusions}
        if len(types) == 1:
            only = next(iter(types))
            if only in _FUSION_BIND_ERRORS:
                return _FUSION_BIND_ERRORS[only]
        return '融合场景需要同时绑定目标检测算法和姿态算法'
    if od_id:
        class_err = missing_detection_class(rules)
        if class_err:
            return class_err
        class_err = classes_outside_allowlist(rules, allowed_class_ids)
        if class_err:
            return class_err
    for fusion in _enabled(fusions):
        class_ids = fusion.get('class_ids') or []
        if not class_ids:
            return _FUSION_CLASS_ERRORS.get(
                fusion.get('type'),
                '融合场景需要选择检测类别',
            )
    return classes_outside_allowlist(fusions, allowed_class_ids)


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
