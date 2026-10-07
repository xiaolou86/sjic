"""
算法目录：上架「算法」（按引擎），任务内挂「规则/场景预设」。

- type / engine：对客户可见的算法能力（通常 1:1，如 object_detection）
- scene_presets：任务里可勾选添加的规则/行为模板（手机、帽子、张望等）
摄像头 mount_position（前/后/侧/正上方）只影响姿态几何，不再使用 camera_role。
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
        'hidden': True,
    },
    'belt_deviation_detection': {
        'label': '皮带跑偏检测',
        'needs_model': True,
        'description': '工业：皮带跑偏',
        'hidden': True,
    },
    'belt_broken_series': {
        'label': '皮带撕裂序列检测',
        'needs_model': True,
        'description': '工业：连续撕裂',
        'hidden': True,
    },
    'belt_broken_high': {
        'label': '高精度皮带撕裂检测',
        'needs_model': True,
        'description': '工业：高精度表面撕裂',
        'hidden': True,
    },
}

CATEGORIES = [
    {'value': 'exam', 'label': '驾考监考'},
    {'value': 'industrial', 'label': '工业检测'},
    {'value': 'generic', 'label': '通用'},
]

CAMERA_MOUNT_POSITIONS = [
    {'value': 'front_top', 'label': '前上方', 'hint': '考生前方高处，能看到脸'},
    {'value': 'back_top', 'label': '后上方', 'hint': '考生后方高处，主要看到后脑/后背'},
    {'value': 'side_top', 'label': '侧上方', 'hint': '侧面高处，以侧脸为主'},
    {'value': 'top', 'label': '正上方', 'hint': '接近天花板垂直向下'},
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
    {
        'id': 'person_fall',
        'type': 'presence',
        'name': '人员倒地',
        'description': '用目标检测模型识别倒地人员（模型需含跌倒类别），不使用姿态关键点',
        'defaults': {
            'alert_type': 'person_fall',
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
        'description': '不看屏幕：左右转头、回头或过度埋头。正常低头看题不算。几何随摄像头安装位置变化。',
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
        'description': '头部相对肩线明显转向一侧（偷看邻座）。正常看屏幕不算。',
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
        'description': '相对看屏幕的正常坐姿，头部进一步埋下（看腿上/桌下）',
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
        'id': 'cover_mouth',
        'type': 'cover_mouth',
        'name': '捂嘴报题',
        'description': '考生捂嘴说话，可能在向场外念题',
        'defaults': {
            'seconds': 3,
            'alert_type': 'cover_mouth',
            'enabled': True,
        },
    },
    {
        'id': 'invigilator_absent',
        'type': 'invigilator_absent',
        'name': '考试员不巡场',
        'description': '考场需 2 名考官站立巡场；站立人数持续少于阈值则告警（默认每 2 分钟判定）',
        'defaults': {
            'seconds': 120,
            'min_standing': 2,
            'alert_type': 'invigilator_absent',
            'enabled': True,
        },
    },
]


# 同一帧需要目标检测框 + 姿态关键点的场景。只在混合任务里可选。
FUSION_SCENE_PRESETS = [
    {
        'id': 'smart_glasses',
        'type': 'smart_glasses',
        'name': 'AI智能眼镜拍摄题目',
        'description': '先检出眼镜，再统计戴镜人员手指触碰镜脚（耳朵附近）的次数',
        'requires': ['object_detection', 'pose_behavior'],
        'defaults': {
            'seconds': 30,
            'min_touches': 3,
            'ear_dist_ratio': 0.28,
            'class_ids': [],
            'alert_type': 'smart_glasses',
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
        'description': '一次推理挂多条规则：缺席、手机、帽子、火情、聚集、滞留、人员倒地等',
        'category': 'exam',
        'parameter_schema': _od_schema(),
    },
    {
        'type': 'pose_behavior',
        'engine': 'pose_behavior',
        'name': '姿态行为检测',
        'description': '一次推理挂多个行为：不看屏幕、张望、捂嘴报题、巡场等',
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
        'hidden': True,
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
    {
        'type': 'belt_deviation_detection',
        'engine': 'belt_deviation_detection',
        'name': '皮带跑偏检测',
        'description': '基于边缘检测和截面分析的皮带跑偏监测',
        'category': 'industrial',
        'hidden': True,
        'parameter_schema': {'ui': {'editor': 'belt_deviation'}},
    },
    {
        'type': 'belt_broken_series',
        'engine': 'belt_broken_series',
        'name': '皮带撕裂与磨损检测',
        'description': '皮带连续撕裂检测',
        'category': 'industrial',
        'hidden': True,
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
    {
        'type': 'belt_broken_high',
        'engine': 'belt_broken_high',
        'name': '高精度皮带表面撕裂检测',
        'description': '高精度皮带表面撕裂检测',
        'category': 'industrial',
        'hidden': True,
        'parameter_schema': {'ui': {'editor': 'belt'}},
    },
]

# 旧版细粒度「一场景一算法」type，启动同步时不再维护（可保留 DB 行以免断任务）
DEPRECATED_SCENE_TYPES = frozenset({
    'gaze_away', 'chin_rest', 'finger_screen', 'person_fall',
    'phone_detect', 'hat_detect', 'exam_area_linger', 'aisle_crowd',
    'fire_smoke', 'camera_blocked',
})


def is_hidden_algorithm(engine=None, algorithm_type=None, category=None) -> bool:
    """矿场皮带类算法先从清单和任务选择里隐藏，实现仍保留。"""
    if category == 'industrial':
        return True
    for key in (engine, algorithm_type):
        meta = ENGINES.get((key or '').strip())
        if meta and meta.get('hidden'):
            return True
    return False


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


def _merge_scene_presets(existing, catalog):
    """按 id 合并：保留已有项，追加目录中新增预设。"""
    existing = list(existing or [])
    catalog = list(catalog or [])
    if not catalog:
        return existing
    by_id = {p.get('id'): dict(p) for p in existing if p.get('id')}
    ordered = []
    seen = set()
    for p in catalog:
        pid = p.get('id')
        if not pid:
            continue
        if pid in by_id:
            # 保留实例侧已改字段，但补齐缺失的 defaults/description
            cur = by_id[pid]
            merged = dict(p)
            merged.update(cur)
            if isinstance(p.get('defaults'), dict):
                merged['defaults'] = {**(p.get('defaults') or {}), **(cur.get('defaults') or {})}
            ordered.append(merged)
        else:
            ordered.append(dict(p))
        seen.add(pid)
    for p in existing:
        pid = p.get('id')
        if pid and pid not in seen:
            ordered.append(dict(p))
            seen.add(pid)
    return ordered


# 合并时从姿态 schema 去掉：跌倒改由目标检测；智能眼镜改由混合任务的融合场景
_POSE_DROPPED_PRESET_IDS = frozenset({'person_fall', 'smart_glasses'})
_POSE_DROPPED_TYPES = frozenset({'fall', 'smart_glasses'})


def merge_catalog_schema(existing_schema, engine: str, *, origin=None) -> dict:
    """用目录补齐/合并 scene_presets / ui / default_task_params，保留 publish_meta 等。"""
    base = schema_for_engine(engine)
    schema = dict(existing_schema or {})
    if base.get('scene_presets'):
        merged_presets = _merge_scene_presets(
            schema.get('scene_presets'), base['scene_presets']
        )
        if engine == 'pose_behavior':
            merged_presets = [
                p for p in merged_presets
                if p.get('id') not in _POSE_DROPPED_PRESET_IDS and p.get('type') not in _POSE_DROPPED_TYPES
            ]
        schema['scene_presets'] = merged_presets
    if not schema.get('ui') and base.get('ui'):
        schema['ui'] = base['ui']
    if 'default_task_params' not in schema and 'default_task_params' in base:
        schema['default_task_params'] = base['default_task_params']
    if origin and not schema.get('origin'):
        schema['origin'] = origin
    return schema


def catalog_for_api():
    visible_products = [p for p in PRODUCT_ALGORITHMS if not p.get('hidden')]
    visible_categories = {p.get('category') for p in visible_products}
    return {
        'engines': [
            {'value': k, **v}
            for k, v in ENGINES.items()
            if not v.get('hidden')
        ],
        'categories': [c for c in CATEGORIES if c['value'] in visible_categories or c['value'] == 'generic'],
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
            for p in visible_products
        ],
        'od_scene_presets': OD_SCENE_PRESETS,
        'pose_scene_presets': POSE_SCENE_PRESETS,
        'fusion_scene_presets': FUSION_SCENE_PRESETS,
        'camera_mount_positions': CAMERA_MOUNT_POSITIONS,
        'alert_type_labels': alert_type_labels(),
    }


def alert_type_labels():
    """alert_type → 客户可读场景名（概览/告警列表用）。"""
    labels = {}
    for preset in OD_SCENE_PRESETS + POSE_SCENE_PRESETS + FUSION_SCENE_PRESETS:
        at = (preset.get('defaults') or {}).get('alert_type')
        if at and preset.get('name'):
            labels[at] = preset['name']
    for product in PRODUCT_ALGORITHMS:
        defaults = (product.get('parameter_schema') or {}).get('default_task_params') or {}
        at = defaults.get('alert_type')
        if at and product.get('name'):
            labels.setdefault(at, product['name'])
        engine = product.get('engine') or product.get('type')
        if engine and product.get('name'):
            labels.setdefault(engine, product['name'])
    for engine, meta in ENGINES.items():
        labels.setdefault(engine, meta.get('label') or engine)
    return labels


def label_for_alert_type(alert_type: str) -> str:
    if not alert_type:
        return '未知场景'
    return alert_type_labels().get(alert_type, alert_type)
