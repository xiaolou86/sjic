"""把正在推理的那一帧画上检测结果，按需回传平台。

只在任务页打开预览时上传。目标检测画框和类别，姿态画骨骼点。
数量是这一帧里达到推理阈值的候选，不是已经触发的告警。
"""
import json
import logging
import queue
import threading
import time

import cv2
import numpy as np

from .base import _POSE_EDGES, _load_cjk_font, _pose_points
from .pose_geometry import keypoint_debug_rows

logger = logging.getLogger('algorithms.preview')

_PREVIEW_INTERVAL = 0.25
_DRAW_LIMIT = 80
_TTL_SEC = 12

_lock = threading.Lock()
_sessions = {}
_api_base = ''
_queue = queue.Queue(maxsize=2)
_worker_started = False
_last_upload_warn = 0.0


def configure_preview(api_base):
    global _api_base
    _api_base = (api_base or '').rstrip('/')


def normalize_labelmap(raw):
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


def set_preview(task_id, enabled, labelmap=None, ttl=_TTL_SEC):
    """平台心跳会反复打开；已经开着时只延长截止时间，避免刷日志。"""
    task_key = _task_key(task_id)
    if task_key is None:
        return
    with _lock:
        if not enabled:
            if _sessions.pop(task_key, None) is not None:
                logger.info(f"Detection preview off task={task_key}")
            return
        session = _sessions.get(task_key)
        created = session is None
        if session is None:
            session = {'last_offer': 0.0, 'labelmap': {}}
        session['deadline'] = time.time() + float(ttl or _TTL_SEC)
        if labelmap:
            session['labelmap'] = normalize_labelmap(labelmap)
        _sessions[task_key] = session
        if created:
            logger.info(f"Detection preview on task={task_key}")


def offer_detection_preview(
    task_id,
    frame,
    *,
    boxes=None,
    persons=None,
    object_threshold=None,
    pose_threshold=None,
    infer_ms=None,
    object_error=False,
    pose_error=False,
    scenes=None,
    occlusion=None,
    _sink=None,
):
    """推理线程里调用。未开预览或距上次不足间隔时直接返回。"""
    try:
        _offer_detection_preview(
            task_id, frame,
            boxes=boxes, persons=persons,
            object_threshold=object_threshold, pose_threshold=pose_threshold,
            infer_ms=infer_ms, object_error=object_error, pose_error=pose_error,
            scenes=scenes, occlusion=occlusion, _sink=_sink,
        )
    except Exception as exc:
        _warn_upload(exc)
        if _sink is not None:
            raise


def _offer_detection_preview(
    task_id,
    frame,
    *,
    boxes=None,
    persons=None,
    object_threshold=None,
    pose_threshold=None,
    infer_ms=None,
    object_error=False,
    pose_error=False,
    scenes=None,
    occlusion=None,
    _sink=None,
):
    task_key = _task_key(task_id)
    if task_key is None or frame is None:
        return
    now = time.time()
    with _lock:
        session = _sessions.get(task_key)
        if session is None or session.get('deadline', 0) <= now:
            if session is not None:
                _sessions.pop(task_key, None)
            return
        if now - session.get('last_offer', 0) < _PREVIEW_INTERVAL:
            return
        session['last_offer'] = now
        labelmap = dict(session.get('labelmap') or {})
        api_base = _api_base
    if not api_base:
        return

    vis, stats = compose_preview(
        frame,
        boxes=boxes,
        persons=persons,
        labelmap=labelmap,
        object_threshold=object_threshold,
        pose_threshold=pose_threshold,
        infer_ms=infer_ms,
        object_error=object_error,
        pose_error=pose_error,
        scenes=scenes,
        occlusion=occlusion,
    )
    if vis is None:
        return
    ok, encoded = cv2.imencode('.jpg', vis, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        return
    url = f"{api_base}/tasks/{task_key}/preview"
    sink = _sink or _enqueue
    sink(url, encoded.tobytes(), stats)


def compose_preview(
    frame,
    *,
    boxes=None,
    persons=None,
    labelmap=None,
    object_threshold=None,
    pose_threshold=None,
    infer_ms=None,
    object_error=False,
    pose_error=False,
    scenes=None,
    occlusion=None,
    draw_limit=_DRAW_LIMIT,
):
    """返回 (画好的 BGR 图, 统计)。boxes/persons 为 None 表示这一路本帧没跑。"""
    if frame is None or not hasattr(frame, 'shape') or frame.size == 0:
        return None, {}
    vis = frame.copy()
    names = labelmap or {}
    stats = {}
    if infer_ms is not None:
        try:
            stats['infer_ms'] = int(round(float(infer_ms)))
        except (TypeError, ValueError):
            pass

    labels = []
    captions = []

    # 先画目标框，再把骨骼叠上去，避免框把关节点盖住。
    if boxes is not None or object_error:
        object_stats, object_labels = _draw_objects(
            vis, [] if object_error else (boxes or []), names, object_threshold, object_error, draw_limit
        )
        stats['object'] = object_stats
        labels.extend(object_labels)
        if object_error:
            captions.append('目标推理失败')
        else:
            captions.append(
                f"目标 {object_stats['count']} / 阈值 {_fmt_threshold(object_threshold)}"
            )

    if occlusion:
        stats['occlusion'] = occlusion
        captions.append(
            f"遮挡 {_fmt_percent(occlusion.get('ratio'))} / 门槛 {_fmt_percent(occlusion.get('cover_ratio'))}"
        )

    if persons is not None or pose_error:
        pose_stats, pose_labels = _draw_pose(
            vis, [] if pose_error else (persons or []), pose_threshold, pose_error, draw_limit
        )
        stats['pose'] = pose_stats
        labels.extend(pose_labels)
        if pose_error:
            captions.append('姿态推理失败')
        else:
            captions.append(
                f"人体 {pose_stats['count']} / 阈值 {_fmt_threshold(pose_threshold)} / 骨骼 {pose_stats['with_skeleton']}"
            )

    if scenes:
        stats['scenes'] = list(scenes)[:12]
    if captions:
        labels.insert(0, (8, 8, '  '.join(captions), (255, 255, 255)))
    _paint_labels(vis, labels)
    return vis, stats


def _draw_objects(vis, boxes, labelmap, threshold, failed, draw_limit):
    ranked = sorted(boxes, key=_box_conf, reverse=True)
    stats = {
        'ok': not failed,
        'threshold': _threshold_value(threshold),
        'count': 0 if failed else len(ranked),
        'shown': 0 if failed else min(len(ranked), draw_limit),
        'classes': [] if failed else _class_summary(ranked, labelmap),
    }
    if failed:
        return stats, []
    labels = []
    for box in ranked[:draw_limit]:
        x1, y1, x2, y2 = _box_xyxy(box)
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        name = _class_name(getattr(box, 'class_id', -1), labelmap)
        labels.append((x1, max(y1 - 18, 2), f"{name} {_box_conf(box):.2f}", (0, 255, 0)))
    return stats, labels


def _draw_pose(vis, persons, threshold, failed, draw_limit):
    ranked = sorted(persons or [], key=lambda item: _box_conf(item[0] if item else None), reverse=True)
    usable = []
    confs = []
    if not failed:
        for box, kps in ranked:
            confs.append(_box_conf(box))
            if _skeleton_usable(kps):
                usable.append(kps)
    stats = {
        'ok': not failed,
        'threshold': _threshold_value(threshold),
        'count': 0 if failed else len(ranked),
        'with_skeleton': 0 if failed else len(usable),
        'shown': 0 if failed else min(len(ranked), draw_limit),
        'max_confidence': 0 if not confs else round(max(confs), 4),
        'people': [] if failed else _people_debug(ranked[:min(3, draw_limit)]),
    }
    if failed:
        return stats, []
    labels = []
    skeletons = []
    for index, (box, kps) in enumerate(ranked[:draw_limit]):
        if _skeleton_usable(kps):
            skeletons.append(kps)
            anchor = _label_anchor(kps, box)
        else:
            x1, y1, x2, y2 = _box_xyxy(box) if box is not None else (8, 28, 8, 28)
            if box is not None:
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 140, 255), 2)
            anchor = (x1, max(y1 - 18, 2))
        if anchor is not None:
            labels.append((anchor[0], anchor[1], f"人{index + 1}", (0, 255, 255)))
    _draw_skeletons(vis, skeletons)
    return stats, labels


def _people_debug(ranked):
    people = []
    for index, (box, kps) in enumerate(ranked):
        points = keypoint_debug_rows(kps)
        missing = [item['name'] for item in points if not item.get('ok')]
        people.append({
            'index': index + 1,
            'confidence': round(_box_conf(box), 2),
            'usable': len(points) - len(missing),
            'missing': missing,
            'points': points,
        })
    return people


def _draw_skeletons(vis, skeletons):
    for kps in skeletons or []:
        pts = _pose_points(kps, 0.25)
        for a, b in _POSE_EDGES:
            if a >= len(pts) or b >= len(pts) or not (pts[a][2] and pts[b][2]):
                continue
            p1 = (int(pts[a][0]), int(pts[a][1]))
            p2 = (int(pts[b][0]), int(pts[b][1]))
            cv2.line(vis, p1, p2, (255, 200, 0), 2, cv2.LINE_AA)
        for x, y, ok in pts:
            if not ok:
                continue
            cv2.circle(vis, (int(x), int(y)), 3, (0, 140, 255), -1, cv2.LINE_AA)


def _class_summary(boxes, labelmap):
    groups = {}
    for box in boxes:
        try:
            class_id = int(getattr(box, 'class_id', -1))
        except (TypeError, ValueError):
            class_id = -1
        group = groups.get(class_id)
        conf = _box_conf(box)
        if group is None:
            groups[class_id] = {
                'id': class_id,
                'name': _class_name(class_id, labelmap),
                'count': 1,
                'max_confidence': round(conf, 4),
            }
        else:
            group['count'] += 1
            if conf > group['max_confidence']:
                group['max_confidence'] = round(conf, 4)
    return sorted(groups.values(), key=lambda item: (-item['count'], item['id']))


def _class_name(class_id, labelmap):
    try:
        key = int(class_id)
    except (TypeError, ValueError):
        return '?'
    name = (labelmap or {}).get(key)
    if name:
        text = str(name).strip()
        return text[:24] if text else f'#{key}'
    return f'#{key}'


def _skeleton_usable(kps):
    if kps is None:
        return False
    try:
        count = len(kps)
    except TypeError:
        return False
    for index in range(min(count, 17)):
        row = kps[index]
        try:
            x, y = float(row[0]), float(row[1])
            conf = float(row[2]) if len(row) > 2 else 1.0
        except (TypeError, ValueError, IndexError):
            continue
        if conf >= 0.25 and x > 0 and y > 0:
            return True
    return False


def _label_anchor(kps, box):
    pts = _pose_points(kps, 0.25)
    visible = [(x, y) for x, y, ok in pts if ok]
    if visible:
        x, y = min(visible, key=lambda item: item[1])
        return int(x), max(int(y) - 18, 2)
    if box is None:
        return None
    x1, y1, _, _ = _box_xyxy(box)
    return x1, max(y1 - 18, 2)


def _box_xyxy(box):
    if box is None:
        return 0, 0, 0, 0
    return (
        int(getattr(box, 'x1', 0)),
        int(getattr(box, 'y1', 0)),
        int(getattr(box, 'x2', 0)),
        int(getattr(box, 'y2', 0)),
    )


def _box_conf(box):
    if box is None:
        return 0.0
    try:
        return float(getattr(box, 'confidence', 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _threshold_value(value):
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _fmt_threshold(value):
    number = _threshold_value(value)
    if number is None:
        return '-'
    return f'{number:.2f}'


def _fmt_percent(value):
    try:
        return f'{float(value):.0%}'
    except (TypeError, ValueError):
        return '-'


def _paint_labels(vis, labels):
    usable = []
    for item in labels or []:
        if not item or not item[2]:
            continue
        usable.append(item)
    if not usable:
        return vis
    font = _load_cjk_font(16)
    if font is None:
        for x, y, text, color in usable:
            if _is_ascii(text):
                cv2.putText(
                    vis, text, (int(x), int(y) + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
                )
        return vis
    try:
        from PIL import Image, ImageDraw
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil, 'RGBA')
        for x, y, text, color in usable:
            x, y = int(x), int(y)
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((x, y), text, font=font)
            else:
                tw, th = draw.textsize(text, font=font)
                bbox = (x, y, x + tw, y + th)
            draw.rectangle(
                [bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1],
                fill=(0, 0, 0, 140),
            )
            draw.text(
                (x, y), text, font=font,
                fill=(int(color[2]), int(color[1]), int(color[0]), 255),
            )
        painted = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        vis[:] = painted
    except Exception:
        logger.debug('preview label paint failed', exc_info=True)
    return vis


def _is_ascii(text):
    try:
        return str(text).isascii()
    except Exception:
        return all(ord(ch) < 128 for ch in str(text))


def _task_key(task_id):
    try:
        return int(task_id)
    except (TypeError, ValueError):
        return None


def _enqueue(url, jpeg, stats):
    _ensure_worker()
    try:
        _queue.put_nowait((url, jpeg, stats))
    except queue.Full:
        try:
            _queue.get_nowait()
        except queue.Empty:
            pass
        try:
            _queue.put_nowait((url, jpeg, stats))
        except queue.Full:
            pass


def _ensure_worker():
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
    threading.Thread(target=_upload_loop, name='detection-preview', daemon=True).start()


def _upload_loop():
    while True:
        url, jpeg, stats = _queue.get()
        try:
            _upload(url, jpeg, stats)
        except Exception as exc:
            _warn_upload(exc)


def _upload(url, jpeg, stats):
    import requests
    response = requests.post(
        url,
        files={'image': ('preview.jpg', jpeg, 'image/jpeg')},
        data={'stats': json.dumps(stats, ensure_ascii=False)},
        timeout=2,
    )
    if not response.ok:
        _warn_upload(f'HTTP {response.status_code}')


def _warn_upload(exc):
    global _last_upload_warn
    now = time.time()
    if now - _last_upload_warn < 5:
        return
    _last_upload_warn = now
    logger.warning('Detection preview failed: %s', exc)
