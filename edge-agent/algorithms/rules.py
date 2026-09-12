"""object_detection 引擎上的时序规则：一次推理、多条规则判定。"""
from shapely.geometry import Point, Polygon


def _class_ok(box, class_ids):
    if not class_ids:
        return True
    return int(getattr(box, 'class_id', 0)) in class_ids


def _boxes_in_roi(boxes, class_ids, roi_polygon):
    matched = []
    for box in boxes:
        if not _class_ok(box, class_ids):
            continue
        if roi_polygon is not None:
            foot = box.foot_center
            if not roi_polygon.contains(Point(foot)):
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
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon)
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
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon)
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
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon)
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
        matched = _boxes_in_roi(boxes, self.class_ids, self._roi_polygon)
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
