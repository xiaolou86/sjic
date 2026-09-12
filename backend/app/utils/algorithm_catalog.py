"""
算法目录：上架「算法」（按引擎），任务内挂「规则/场景预设」。

- type / engine：对客户可见的算法能力（通常 1:1，如 object_detection）
- scene_presets：任务里可勾选添加的规则/行为模板（手机、帽子、张望等）
机位用摄像头名称表达，不再使用 camera_role。
"""

ENGINES = {
    'object_detection': {
        'label': '目标检测',
        'needs_model': True,
        'description': 'YOLO 目标检测：一次推理，任务内可挂多条规则（出现/驻留/缺席/聚集等）',
    },
    'pose_behavior': {
        'label': '姿态行为检测',
        'needs_model': True,
        'description': '人体姿态：一次推理，任务内可挂多个行为（张望/低头/手托下巴等）',
    },
    'camera_health': {
        'label': '画面健康检测',
        'needs_model': False,
        'description': '无模型：黑屏、遮挡等画面异常',
    },
    'mouse_idle': {
        'label': '鼠标空闲检测',
        'needs_model': False,
        'description': '无视觉模型：依赖边缘鼠标活动时间戳（有鼠标考场）',
    },
    'belt_broken': {
        'label': '皮带破损检测',
        'needs_model': True,
        'description': '工业：皮带表面故障',
    },
    'belt_deviation_detection': {
        'label': '皮带跑偏检测',
        'needs_model': True,
        'description': '工业：皮带跑偏',
    },
    'belt_broken_series': {
        'label': '皮带撕裂序列检测',
        'needs_model': True,
        'description': '工业：连续撕裂',
    },
    'belt_broken_high': {
        'label': '高精度皮带撕裂检测',
        'needs_model': True,
        'description': '工业：高精度表面撕裂',
    },
}

CATEGORIES = [
    {'value': 'exam', 'label': '驾考监考'},
    {'value': 'industrial', 'label': '工业检测'},
    {'value': 'generic', 'label': '通用'},
]

# 目标检测任务内可添加的场景/规则预设（class_ids 发布后按模型 labelmap 调整）
OD_SCENE_PRESETS = [
    {
        'id': 'person_absence',
        'type': 'absence',
        'name': '人员缺席',
        'description': '区域内持续无人超过设定时长',
        'defaults': {
            'absent_seconds': 600,
            'alert_type': 'person_absence',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'person_linger',
        'type': 'linger',
        'name': '人员滞留',
        'description': '区域内持续有人超过设定时长（如考试区违规滞留）',
        'defaults': {
            'linger_seconds': 300,
            'alert_type': 'exam_area_linger',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'phone_detect',
        'type': 'presence',
        'name': '识别手机',
        'description': '出现手机即告警（需模型含 phone 类）',
        'defaults': {
            'alert_type': 'phone_detect',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'hat_detect',
        'type': 'presence',
        'name': '识别戴帽',
        'description': '出现帽子即告警（需模型含 hat 类）',
        'defaults': {
            'alert_type': 'hat_detect',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'fire_smoke',
        'type': 'presence',
        'name': '火情/烟雾',
        'description': '出现火情或烟雾（需模型含 fire/smoke 类）',
        'defaults': {
            'alert_type': 'fire_smoke',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'aisle_crowd',
        'type': 'crowd_count',
        'name': '通道人员聚集',
        'description': '区域内人数持续超限',
        'defaults': {
            'min_count': 5,
            'seconds': 10,
            'alert_type': 'aisle_crowd',
            'class_ids': [0],
            'enabled': True,
        },
    },
    {
        'id': 'generic_presence',
        'type': 'presence',
        'name': '区域内出现',
        'description': '自定义类别在区域内出现',
        'defaults': {
            'alert_type': 'object_detection',
            'class_ids': [0],
            'enabled': True,
        },
    },
]

POSE_SCENE_PRESETS = [
    {
        'id': 'not_looking_screen',
        'type': 'gaze_away',
        'name': '长时间不看屏幕',
        'description': '偏头或低头超过阈值并持续一段时间',
        'defaults': {
            'seconds': 15,
            'yaw_degrees': 25,
            'pitch_degrees': 25,
            'alert_type': 'gaze_away',
            'enabled': True,
        },
    },
    {
        'id': 'look_aside',
        'type': 'look_aside',
        'name': '左右张望',
        'description': '单边偏航超过设定角度',
        'defaults': {
            'seconds': 3,
            'yaw_degrees': 45,
            'alert_type': 'look_aside',
            'enabled': True,
        },
    },
    {
        'id': 'head_down',
        'type': 'head_down',
        'name': '长时间低头',
        'description': '低头俯仰超过阈值并持续一段时间',
        'defaults': {
            'seconds': 15,
            'pitch_degrees': 30,
            'alert_type': 'head_down',
            'enabled': True,
        },
    },
    {
        'id': 'chin_rest',
        'type': 'chin_rest',
        'name': '手托下巴',
        'description': '手腕靠近下颌（袖口藏摄嫌疑）',
        'defaults': {
            'seconds': 5,
            'alert_type': 'chin_rest',
            'enabled': True,
        },
    },
    {
        'id': 'finger_screen',
        'type': 'finger_point',
        'name': '手指屏幕',
        'description': '站立人员伸臂指向/触摸屏幕',
        'defaults': {
            'seconds': 2,
            'require_standing': True,
            'alert_type': 'finger_screen',
            'enabled': True,
        },
    },
    {
        'id': 'person_fall',
        'type': 'fall',
        'name': '人员倒地',
        'description': '姿态接近倒地',
        'defaults': {
            'seconds': 1.5,
            'alert_type': 'person_fall',
            'enabled': True,
        },
    },
]


def _od_schema():
    return {
        'scene_presets': OD_SCENE_PRESETS,
        'ui': {'editor': 'detection_rules'},
        'default_task_params': {'rules': []},
    }


def _pose_schema():
    return {
        'scene_presets': POSE_SCENE_PRESETS,
        'ui': {'editor': 'pose_behavior'},
        'default_task_params': {'behaviors': []},
    }


# 上架的「算法」= 引擎级能力（客户建任务时选这个，再往里加多条规则/场景）
PRODUCT_ALGORITHMS = [
    {
        'type': 'object_detection',
        'engine': 'object_detection',
        'name': '目标检测',
        'description': '一次推理挂多条规则：缺席、手机、帽子、火情、聚集、滞留等',
        'category': 'exam',
        'parameter_schema': _od_schema(),
    },
    {
        'type': 'pose_behavior',
        'engine': 'pose_behavior',
        'name': '姿态行为检测',
        'description': '一次推理挂多个行为：不看屏幕、张望、低头、手托下巴、手指屏幕、倒地等',
        'category': 'exam',
        'parameter_schema': _pose_schema(),
    },
    {
        'type': 'camera_health',
        'engine': 'camera_health',
        'name': '画面健康检测',
        'description': '摄像头黑屏或被遮挡',
        'category': 'exam',
        'parameter_schema': {
            'ui': {'editor': 'camera_health'},
            'default_task_params': {
                'black_ratio': 0.85,
                'variance_threshold': 12.0,
                'seconds': 3,
                'alert_type': 'camera_blocked',
            },
        },
    },
    {
        'type': 'mouse_idle',
        'engine': 'mouse_idle',
        'name': '鼠标空闲检测',
        'description': '超过设定时长无鼠标操作（有鼠标考场）',
        'category': 'exam',
        'parameter_schema': {
            'ui': {'editor': 'mouse_idle'},
            'default_task_params': {
                'idle_seconds': 60,
                'alert_type': 'mouse_idle',
            },
        },
    },
    {
        'type': 'belt_broken',
        'engine': 'belt_broken',
        'name': '皮带表面故障检测',
        'description': '检测皮带表面破损划伤',
        'category': 'industrial',
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
    {
        'type': 'belt_deviation_detection',
        'engine': 'belt_deviation_detection',
        'name': '皮带跑偏检测',
        'description': '基于边缘检测和截面分析的皮带跑偏监测',
        'category': 'industrial',
        'parameter_schema': {'ui': {'editor': 'belt_deviation'}},
    },
    {
        'type': 'belt_broken_series',
        'engine': 'belt_broken_series',
        'name': '皮带撕裂与磨损检测',
        'description': '皮带连续撕裂检测',
        'category': 'industrial',
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
    {
        'type': 'belt_broken_high',
        'engine': 'belt_broken_high',
        'name': '高精度皮带表面撕裂检测',
        'description': '高精度皮带表面撕裂检测',
        'category': 'industrial',
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
]

# 旧版细粒度「一场景一算法」type，启动同步时不再维护（可保留 DB 行以免断任务）
DEPRECATED_SCENE_TYPES = frozenset({
    'gaze_away', 'chin_rest', 'finger_screen', 'person_fall',
    'phone_detect', 'hat_detect', 'exam_area_linger', 'aisle_crowd',
    'fire_smoke', 'camera_blocked',
})


def engine_needs_model(engine: str) -> bool:
    meta = ENGINES.get(engine) or {}
    return bool(meta.get('needs_model', True))


def get_product(product_type: str):
    for item in PRODUCT_ALGORITHMS:
        if item['type'] == product_type:
            return item
    return None


def get_product_by_engine(engine: str):
    engine = (engine or '').strip()
    for item in PRODUCT_ALGORITHMS:
        if item.get('engine') == engine or item.get('type') == engine:
            return item
    return None


def schema_for_engine(engine: str) -> dict:
    """按引擎取完整 parameter_schema（含 scene_presets）。"""
    product = get_product_by_engine(engine)
    if not product:
        return {}
    return dict(product.get('parameter_schema') or {})


def merge_catalog_schema(existing_schema, engine: str, *, origin=None) -> dict:
    """用目录补齐缺失的 scene_presets / ui / default_task_params，保留 publish_meta 等。"""
    base = schema_for_engine(engine)
    schema = dict(existing_schema or {})
    if not schema.get('scene_presets') and base.get('scene_presets'):
        schema['scene_presets'] = base['scene_presets']
    if not schema.get('ui') and base.get('ui'):
        schema['ui'] = base['ui']
    if 'default_task_params' not in schema and 'default_task_params' in base:
        schema['default_task_params'] = base['default_task_params']
    if origin and not schema.get('origin'):
        schema['origin'] = origin
    return schema


def catalog_for_api():
    return {
        'engines': [{'value': k, **v} for k, v in ENGINES.items()],
        'categories': CATEGORIES,
        'products': [
            {
                'type': p['type'],
                'engine': p['engine'],
                'name': p['name'],
                'description': p['description'],
                'category': p['category'],
                'parameter_schema': p.get('parameter_schema') or {},
                'needs_model': engine_needs_model(p.get('engine') or p['type']),
            }
            for p in PRODUCT_ALGORITHMS
        ],
        'od_scene_presets': OD_SCENE_PRESETS,
        'pose_scene_presets': POSE_SCENE_PRESETS,
    }
