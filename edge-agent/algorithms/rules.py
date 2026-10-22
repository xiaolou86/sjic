"""object_detection 引擎上的时序规则：一次推理、多条规则判定。"""
from shapely.geometry import Point, Polygon


def _class_ok(box, class_ids):
    if not class_ids:
        return True
    return int(getattr(box, 'class_id', 0)) in class_ids


def _point_in_polygon(polygon, x, y):
    try:
        return bool(polygon.contains(Point((float(x), float(y)))))
    except Exception:
        return False


def _object_in_roi(box, roi_polygon):
    """眼镜、手表这类目标用框是否沾到区域，不用脚点。

    脚点是给人站在哪一块区域用的。眼镜框的底边常常落在脸部区域外面，
    只看脚点会把已经框住的眼镜、手表丢掉。
    """
    if roi_polygon is None:
        return True
    try:
        x1, y1 = float(box.x1), float(box.y1)
        x2, y2 = float(box.x2), float(box.y2)
    except (TypeError, ValueError, AttributeError):
        return False
    samples = (
        ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
        (x1, y1),
        (x2, y1),
        (x1, y2),
        (x2, y2),
    )
    return any(_point_in_polygon(roi_polygon, x, y) for x, y in samples)


def _boxes_in_roi(boxes, class_ids, roi_polygon, min_confidence=None, roi_mode='foot'):
    matched = []
    for box in boxes:
        if min_confidence is not None:
            try:
                if float(getattr(box, 'confidence', 0) or 0) < float(min_confidence):
                    continue
            except (TypeError, ValueError):
                continue
        if not _class_ok(box, class_ids):
            continue
        if roi_polygon is not None:
            if roi_mode == 'overlap':
                inside = _object_in_roi(box, roi_polygon)
            else:
                foot = getattr(box, 'foot_center', None)
                inside = foot is not None and _point_in_polygon(roi_polygon, foot[0], foot[1])
            if not inside:
                continue
        matched.append(box)
    return matched


class BaseRule:
    def __init__(self, spec, roi_points, alert_cooldown_sec, is_point_in_roi=None):
        self.spec = spec or {}
        self.roi_points = roi_points
        per_rule = self.spec.get('alert_cooldown_sec')
        self.alert_cooldown_sec = max(int(per_rule if per_rule is not None else (alert_cooldown_sec or 0)), 0)
        self.enabled = bool(self.spec.get('enabled', True))
        self.id = self.spec.get('id') or self.spec.get('type') or 'rule'
        self.rule_type = self.spec.get('type')
        self.name = self.spec.get('name') or self.rule_type
        self.alert_type = self.spec.get('alert_type') or self.rule_type or 'object_detection'
        raw_ids = self.spec.get('class_ids')
        if raw_ids is None:
            self.class_ids = [0]
        else:
            self.class_ids = [int(x) for x in raw_ids]
        self.min_confidence = self.spec.get('_min_confidence')
        self._last_alert_time = None
        self._state_since = None
        if roi_points and len(roi_points) >= 3:
            self._roi_polygon = Polygon(roi_points)
        else:
            self._roi_polygon = None

    def _cooldown_ok(self, now):
        if self._last_alert_time is None:
            return True
        return (now - self._last_alert_time).total_seconds() >= self.alert_cooldown_sec

    def _hit(self, now, matched, confidence):
        self._last_alert_time = now
        return {
            'rule_id': self.id,
            'rule_name': self.name,
            'alert_type': self.alert_type,
            'confidence': confidence,
            'boxes': matched,
        }

    def evaluate(self, boxes, now, logger):
        raise NotImplementedError


class PresenceRule(BaseRule):
    def evaluate(self, boxes, now, logger):
        matched = _boxes_in_roi(
            boxes, self.class_ids, self._roi_polygon, self.min_confidence, roi_mode='overlap',
        )
        if not matched or not self._cooldown_ok(now):
            return None
        conf = max(b.confidence for b in matched)
        logger.info(f"Rule[{self.id}] presence hit, count={len(matched)}")
        return self._hit(now, matched, conf)


class LingerRule(BaseRule):
    def __init__(self, spec, roi_points, alert_cooldown_sec, is_point_in_roi=None):
        super().__init__(spec, roi_points, alert_cooldown_sec, is_point_in_roi)
        self.linger_seconds = float(self.spec.get('linger_seconds', 5))

    def evaluate(self, boxes, now, logger):
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon, self.min_confidence)
        if not matched:
            self._state_since = None
            return None
        if self._state_since is None:
            self._state_since = now
            return None
        elapsed = (now - self._state_since).total_seconds()
        if elapsed < self.linger_seconds or not self._cooldown_ok(now):
            return None
        conf = max(b.confidence for b in matched)
        logger.info(f"Rule[{self.id}] linger hit after {elapsed:.1f}s, count={len(matched)}")
        self._state_since = now
        return self._hit(now, matched, conf)


class AbsenceRule(BaseRule):
    def __init__(self, spec, roi_points, alert_cooldown_sec, is_point_in_roi=None):
        super().__init__(spec, roi_points, alert_cooldown_sec, is_point_in_roi)
        self.absent_seconds = float(self.spec.get('absent_seconds', 600))

    def evaluate(self, boxes, now, logger):
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon, self.min_confidence)
        if matched:
            self._state_since = None
            return None
        if self._state_since is None:
            self._state_since = now
            return None
        elapsed = (now - self._state_since).total_seconds()
        if elapsed < self.absent_seconds or not self._cooldown_ok(now):
            return None
        logger.info(f"Rule[{self.id}] absence hit after {elapsed:.1f}s")
        self._state_since = now
        return self._hit(now, [], 1.0)


class CrowdCountRule(BaseRule):
    """区域内目标数持续 >= min_count 超过 seconds。"""

    def __init__(self, spec, roi_points, alert_cooldown_sec, is_point_in_roi=None):
        super().__init__(spec, roi_points, alert_cooldown_sec, is_point_in_roi)
        self.min_count = int(self.spec.get('min_count', 5))
        self.seconds = float(self.spec.get('seconds', 10))

    def evaluate(self, boxes, now, logger):
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon, self.min_confidence)
        if len(matched) < self.min_count:
            self._state_since = None
            return None
        if self._state_since is None:
            self._state_since = now
            return None
        elapsed = (now - self._state_since).total_seconds()
        if elapsed < self.seconds or not self._cooldown_ok(now):
            return None
        conf = max(b.confidence for b in matched)
        logger.info(
            f"Rule[{self.id}] crowd_count hit after {elapsed:.1f}s, "
            f"count={len(matched)} >= {self.min_count}"
        )
        self._state_since = now
        return self._hit(now, matched, conf)


RULE_CLASS_MAP = {
    'presence': PresenceRule,
    'linger': LingerRule,
    'absence': AbsenceRule,
    'crowd_count': CrowdCountRule,
}

# 只统计姿态检出的人，不看关键点姿态。class_ids 清空后，每条姿态框都算一个人。
PERSON_COUNT_TYPES = frozenset({'absence', 'linger', 'crowd_count'})


def person_count_specs(behaviors):
    specs = []
    for spec in behaviors or []:
        if not isinstance(spec, dict) or spec.get('type') not in PERSON_COUNT_TYPES:
            continue
        copied = dict(spec)
        copied['class_ids'] = []
        specs.append(copied)
    return specs


def filter_persons_roi(persons, roi_polygon):
    """推理后过滤。没有多边形时保留全部检出的人。"""
    if roi_polygon is None:
        return list(persons or [])
    kept = []
    for box, kps in persons or []:
        if box is None:
            continue
        foot = getattr(box, 'foot_center', None)
        if foot is None:
            continue
        if roi_polygon.contains(Point(foot)):
            kept.append((box, kps))
    return kept


def behavior_rois(behaviors, transform_roi):
    """每个姿态场景一块区域。未标注时多边形为空，表示整帧。"""
    rois = {}
    for spec in behaviors or []:
        if not isinstance(spec, dict):
            continue
        bid = spec.get('id') or spec.get('type')
        points = transform_roi(spec.get('detection_region'))
        polygon = Polygon(points) if points and len(points) >= 3 else None
        rois[bid] = (polygon, points if polygon is not None else None)
    return rois


def person_count_message(spec, btype, hit):
    name = (spec or {}).get('name') or btype
    count = len((hit or {}).get('boxes') or [])
    if btype == 'absence':
        return f"行为[{name}] 持续无人"
    if btype == 'linger':
        return f"行为[{name}] 持续有人 {count} 人"
    return f"行为[{name}] 人数 {count} ≥ {(spec or {}).get('min_count', 5)}"


def _class_id_text(class_ids):
    if not class_ids:
        return '未选'
    return '、'.join(str(int(class_id)) for class_id in class_ids)


def _confidence_text(value):
    try:
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return '不限'


def explain_detection_rules(rules, boxes, now, task_start=None, task_end=None):
    """本帧目标检测场景说明。不改冷却，也不触发告警。"""
    from utils.schedule import is_item_active_now

    rows = []
    for rule in rules or []:
        name = rule.name or rule.alert_type or '检测场景'
        note = getattr(rule, '_class_note', '') or ''
        if not is_item_active_now(now, rule.spec, task_start, task_end):
            reason = '当前不在该场景的生效时段'
        elif rule.rule_type != 'presence':
            reason = f"已调用{rule.rule_type}判定"
        else:
            class_hits = _boxes_in_roi(
                boxes, rule.class_ids, None, rule.min_confidence, roi_mode='overlap',
            )
            region_hits = _boxes_in_roi(
                boxes, rule.class_ids, rule._roi_polygon, rule.min_confidence, roi_mode='overlap',
            )
            ids = _class_id_text(rule.class_ids)
            threshold = _confidence_text(rule.min_confidence)
            if not class_hits:
                reason = (
                    f"已调用出现判定。本帧没有类别 {ids}、置信度≥{threshold} 的目标"
                )
                hit = False
            elif not region_hits:
                reason = f"类别 {ids} 有 {len(class_hits)} 个框，但没有沾到标注区域"
                hit = False
            elif not rule._cooldown_ok(now):
                reason = f"类别 {ids} 本帧有 {len(region_hits)} 个框，还在告警冷却里"
                hit = False
            else:
                reason = f"类别 {ids} 本帧有 {len(region_hits)} 个框，出现即告警"
                hit = True
            if note:
                reason = f"{note}。{reason}"
            rows.append({
                'name': name,
                'type': rule.alert_type,
                'people': [{'hit': hit, 'reason': reason}],
            })
            if len(rows) >= 8:
                break
            continue
        if note:
            reason = f"{note}。{reason}"
        rows.append({
            'name': name,
            'type': rule.alert_type,
            'reason': reason,
            'people': [],
        })
        if len(rows) >= 8:
            break
    return rows


def build_rules(raw_rules, transform_roi, alert_cooldown_sec, is_point_in_roi, logger):
    rules = []
    for spec in raw_rules or []:
        if not spec or spec.get('enabled', True) is False:
            continue
        rtype = spec.get('type')
        cls = RULE_CLASS_MAP.get(rtype)
        if not cls:
            logger.warning(f"Unknown detection rule type: {rtype}, skipped")
            continue
        roi_points = transform_roi(spec.get('detection_region'))
        rules.append(cls(spec, roi_points, alert_cooldown_sec, is_point_in_roi))
        logger.info(f"Loaded rule {spec.get('id')}/{rtype} name={spec.get('name')}")
    return rules
