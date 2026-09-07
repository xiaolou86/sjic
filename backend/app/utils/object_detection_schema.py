"""object_detection 引擎支持的规则类型（算法模板 schema）。"""

OBJECT_DETECTION_RULE_TYPES = [
    {
        'type': 'linger',
        'name': '区域内驻留',
        'description': '区域内持续有目标超过设定时长后告警（如考台周边协助答题）',
        'defaults': {
            'linger_seconds': 5,
            'alert_type': 'exam_desk_linger',
            'class_ids': [0],
            'enabled': True,
        },
        'fields': ['linger_seconds', 'class_ids', 'detection_region'],
    },
    {
        'type': 'absence',
        'name': '区域内缺席',
        'description': '区域内持续无目标超过设定时长后告警（如考官长时间不巡考）',
        'defaults': {
            'absent_seconds': 600,
            'alert_type': 'invigilator_absent',
            'class_ids': [0],
            'enabled': True,
        },
        'fields': ['absent_seconds', 'class_ids', 'detection_region'],
    },
    {
        'type': 'presence',
        'name': '区域内出现',
        'description': '区域内出现目标即告警（受任务「告警间隔」限制）',
        'defaults': {
            'alert_type': 'object_detection',
            'class_ids': [0],
            'enabled': True,
        },
        'fields': ['class_ids', 'detection_region'],
    },
]
