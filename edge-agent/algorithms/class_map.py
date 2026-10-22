"""把场景里选的类别号对齐到检测模型的真实类别。

任务保存的是标注表里的 id。权重文件里的类别号若和标注表不一致，
同名时改用模型的号。否则推理会按错误的号过滤，眼镜和手表一个框都不会回来。
"""


def model_class_names(runtime_obj):
    """runtime 里 YOLO 的 names。没有就返回空字典，调用方保持原类别号。"""
    model = getattr(runtime_obj, 'model', None)
    raw = getattr(model, 'names', None) if model is not None else None
    if raw is None:
        raw = getattr(runtime_obj, 'names', None)
    out = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = enumerate(raw)
    else:
        return out
    for key, value in items:
        try:
            class_id = int(key)
        except (TypeError, ValueError):
            continue
        name = str(value or '').strip()
        if name:
            out[class_id] = name
    return out


def label_names_from(raw):
    """标注表收成 {类别号: 名称}。列表、字典、字符串键都可以。"""
    out = {}
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for key, value in raw.items():
            if isinstance(value, dict):
                items.append(value)
            else:
                items.append({'id': key, 'name': value})
    else:
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            class_id = int(item.get('id'))
        except (TypeError, ValueError):
            continue
        name = str(item.get('name') or '').strip()
        if name:
            out[class_id] = name
    return out


# 标注表常用中文，权重里常见英文。只在所选号不在模型里时，才按这些别名改号。
_NAME_ALIASES = {
    '眼镜': ('glasses', 'eyeglasses', 'eyewear', 'sunglass', 'sunglasses'),
    '手表': ('watch', 'wristwatch', 'smartwatch', 'smart watch'),
    '手机': ('phone', 'cell phone', 'cellphone', 'mobile phone'),
    '帽子': ('hat', 'cap'),
    'glasses': ('眼镜',),
    'eyeglasses': ('眼镜',),
    'watch': ('手表',),
    'wristwatch': ('手表',),
    'phone': ('手机',),
    'cell phone': ('手机',),
    'hat': ('帽子',),
}


def _ids(raw_ids):
    found = []
    for raw in raw_ids or []:
        try:
            found.append(int(raw))
        except (TypeError, ValueError):
            continue
    return found


def align_class_ids(class_ids, label_names, model_names):
    """返回 (对齐后的类别号, 说明)。说明只在改号或模型里没有这个号时出现。"""
    label_names = label_names or {}
    model_names = model_names or {}
    by_name = {}
    for class_id, name in model_names.items():
        key = str(name).strip().lower()
        if key and key not in by_name:
            by_name[key] = int(class_id)
    aligned = []
    notes = []
    for class_id in _ids(class_ids):
        label = label_names.get(class_id)
        label_key = str(label).strip().lower() if label else ''
        mapped = by_name.get(label_key) if label_key else None
        # 号还在模型里时保留。中文标注对英文类别名是正常情况，不能因为名字不同就改号。
        if mapped is None and label_key and class_id not in model_names:
            for alias in _NAME_ALIASES.get(label_key, ()):
                mapped = by_name.get(alias)
                if mapped is not None:
                    break
        if mapped is not None and mapped != class_id:
            aligned.append(mapped)
            model_label = model_names.get(mapped) or label
            notes.append(f"类别 {class_id}（{label}）按模型改到 {mapped}（{model_label}）")
            continue
        if model_names and class_id not in model_names:
            listing = '、'.join(
                f"{index}:{model_names[index]}" for index in sorted(model_names)[:8]
            )
            notes.append(f"类别 {class_id} 不在检测模型里，模型有 {listing}")
        aligned.append(class_id)
    return aligned, notes


def apply_model_class_ids(rules, specs, runtime_obj, labelmap, logger):
    """就地改规则和融合场景的 class_ids。模型没有 names 时不动。"""
    model_names = model_class_names(runtime_obj)
    if not model_names:
        return
    label_names = label_names_from(labelmap)
    for rule in rules or []:
        aligned, notes = align_class_ids(getattr(rule, 'class_ids', None), label_names, model_names)
        if aligned != _ids(getattr(rule, 'class_ids', None)):
            rule.class_ids = aligned
        if notes:
            rule._class_note = '；'.join(notes)
            logger.warning(f"Rule[{getattr(rule, 'id', '')}] {rule._class_note}")
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        aligned, notes = align_class_ids(spec.get('class_ids'), label_names, model_names)
        if aligned != _ids(spec.get('class_ids')):
            spec['class_ids'] = aligned
        if notes:
            spec['_class_note'] = '；'.join(notes)
            logger.warning(
                f"Scene[{spec.get('id') or spec.get('type')}] {spec['_class_note']}"
            )
