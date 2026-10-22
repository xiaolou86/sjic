"""从已加载的权重里读类别号和名称。"""


def names_dict(raw):
    """YOLO 的 names 可能是 {id: name}，也可能是按序号排的列表。"""
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


def read_ultralytics_names(model):
    """ultralytics 把类别表放在 model.names。导出时嵌进权重的也能读到。"""
    names = names_dict(getattr(model, 'names', None))
    if names:
        return names
    inner = getattr(model, 'model', None)
    return names_dict(getattr(inner, 'names', None) if inner is not None else None)


def format_class_names(names):
    if not names:
        return ''
    return ', '.join(f'{class_id}:{names[class_id]}' for class_id in sorted(names))
