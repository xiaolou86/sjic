from abc import ABC, abstractmethod
from datetime import datetime
import cv2
import os
from shapely.geometry import Point, Polygon
import numpy as np

def effective_confidence(spec, task_confidence, default=0.5):
    """场景单独设置了置信度时以场景为准，否则用任务置信度。"""
    try:
        task_v = float(task_confidence)
    except (TypeError, ValueError):
        task_v = float(default)
    raw = spec.get('confidence') if isinstance(spec, dict) else None
    if raw is None or raw == '':
        return task_v
    try:
        return float(raw)
    except (TypeError, ValueError):
        return task_v


class BaseAlgorithm(ABC):
    """边缘端算法纯净抽象基类，不依赖任何数据库和 Web 框架"""

    @abstractmethod
    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        """
        处理视频流
        :param camera_stream: cv2.VideoCapture() 返回的对象
        :param config_dict: 从云端获取的任务配置，包含算法参数、阈值等
        :param logger: 标准的 Python logging logger
        :param stop_event: threading.Event() 用于安全退出循环
        :param on_alert: 告警回调函数 fn(alert_type, confidence, image_frame)
        :param runtime: BaseRuntime 推理后端实例 (由 TaskManager 注入)
        """
        pass

    def need_alert_again(self, last_alert_time, alert_threshold, logger):
        """判断是否需要再次告警"""
        if last_alert_time is None:
            return True
        seconds_passed = (datetime.now() - last_alert_time).total_seconds()
        logger.debug(f"Time since last alert: {seconds_passed}s. Threshold: {alert_threshold}s")
        return seconds_passed >= alert_threshold

    def is_point_in_roi(self, point, points, logger=None):
        """
        判断点是否在检测区域内
        :param point: 点 (x, y)
        :param points: 检测区域的边界点列表 [(x1, y1), (x2, y2), ..., (xn, yn)]
        :return: bool
        """
        center_point = Point(point)
        roi_polygon = Polygon(points)
        return roi_polygon.contains(center_point)

    def draw_and_get_frame(self, frame, detection_result=None):
        """
        绘制检测结果到帧上。
        兼容新的 DetectionResult 和原始的 ultralytics results。
        """
        from runtime.base_runtime import DetectionResult

        if detection_result is None:
            return frame

        # 如果是统一的 DetectionResult 对象
        if isinstance(detection_result, DetectionResult):
            # 如果有原始 ultralytics 结果，优先用 plot()（效果更好）
            if detection_result._raw is not None:
                try:
                    raw = detection_result._raw
                    if hasattr(raw, '__len__') and len(raw) > 0:
                        plotted = raw[0].plot()
                        if hasattr(plotted, 'cpu'):
                            plotted = plotted.cpu().numpy()
                        return plotted
                except Exception:
                    pass
            # 降级：用通用绘制
            return detection_result.draw_on_frame(frame)

        # 兼容旧的列表格式 (ultralytics results)
        if isinstance(detection_result, list) and len(detection_result) > 0:
            try:
                plotted_img = detection_result[0].plot()
                if hasattr(plotted_img, 'cpu'):
                    plotted_img = plotted_img.cpu().numpy()
                return plotted_img
            except Exception:
                pass

        return frame

    def draw_alert_overlay(self, frame, boxes=None, roi_points=None, caption=None, skeletons=None):
        """在告警截图上画规则 ROI、检测框、姿态骨骼和说明文字。"""
        vis = frame.copy()
        _draw_pose_skeletons(vis, skeletons)
        if roi_points and len(roi_points) >= 3:
            pts = np.array(roi_points, dtype=np.int32).reshape((-1, 1, 2))
            overlay = vis.copy()
            cv2.fillPoly(overlay, [pts], (0, 255, 255))
            vis = cv2.addWeighted(overlay, 0.18, vis, 0.82, 0)
            cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 255), thickness=1)

        for box in boxes or []:
            x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 1)
            label = f"cls{getattr(box, 'class_id', 0)}:{float(box.confidence):.2f}"
            vis = _put_text(vis, label, (x1, max(y1 - 16, 2)), color_bgr=(0, 255, 0))
            if hasattr(box, 'foot_center'):
                fx, fy = box.foot_center
                cv2.circle(vis, (int(fx), int(fy)), 2, (0, 0, 255), 1, cv2.LINE_AA)

        if caption:
            vis = _put_text(vis, caption, (8, 8), color_bgr=(255, 255, 255))
        return vis


# COCO-17：头、肩、手臂、躯干、腿。与姿态判断使用的关键点一致。
_POSE_EDGES = (
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6),
    (5, 7), (7, 9),
    (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
)


def _pose_points(kps, min_conf=0.25):
    if kps is None:
        return []
    points = []
    for i in range(len(kps)):
        row = kps[i]
        x, y = float(row[0]), float(row[1])
        conf = float(row[2]) if len(row) > 2 else 1.0
        points.append((x, y, conf >= min_conf and x > 0 and y > 0))
    return points


def _draw_pose_skeletons(vis, skeletons, min_conf=0.25):
    """把用于判断的可见骨骼点和连线画到告警图上。"""
    if vis is None or not skeletons:
        return vis
    for kps in skeletons:
        pts = _pose_points(kps, min_conf)
        for a, b in _POSE_EDGES:
            if a >= len(pts) or b >= len(pts) or not (pts[a][2] and pts[b][2]):
                continue
            p1 = (int(pts[a][0]), int(pts[a][1]))
            p2 = (int(pts[b][0]), int(pts[b][1]))
            cv2.line(vis, p1, p2, (255, 200, 0), 1, cv2.LINE_AA)
        for x, y, ok in pts:
            if not ok:
                continue
            cv2.circle(vis, (int(x), int(y)), 2, (0, 140, 255), 1, cv2.LINE_AA)
    return vis


_FONT_CACHE = {}


def _load_cjk_font(size=14):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    try:
        from PIL import ImageFont
    except Exception:
        _FONT_CACHE[size] = None
        return None
    candidates = [
        os.environ.get('SJIC_CJK_FONT'),
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            font = ImageFont.truetype(path, size)
            _FONT_CACHE[size] = font
            return font
        except Exception:
            continue
    _FONT_CACHE[size] = None
    return None


def _put_text(img, text, origin, color_bgr=(255, 255, 255)):
    """优先用系统中文字体画说明，没有则退回 OpenCV 拉丁字。"""
    if not text:
        return img
    x, y = int(origin[0]), int(origin[1])
    font = _load_cjk_font(14)
    if font is not None:
        try:
            from PIL import Image, ImageDraw
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            draw = ImageDraw.Draw(pil, 'RGBA')
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((x, y), text, font=font)
            else:
                tw, th = draw.textsize(text, font=font)
                bbox = (x, y, x + tw, y + th)
            draw.rectangle(
                [bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1],
                fill=(0, 0, 0, 120),
            )
            draw.text(
                (x, y),
                text,
                font=font,
                fill=(color_bgr[2], color_bgr[1], color_bgr[0], 255),
            )
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            pass
    # OpenCV 默认字体不支持中文，强行绘制会产生方框/乱码；无 CJK 字体时跳过非 ASCII
    try:
        ascii_only = text.isascii()
    except Exception:
        ascii_only = all(ord(ch) < 128 for ch in str(text))
    if ascii_only:
        cv2.putText(
            img, text, (x, y + 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color_bgr, 1, cv2.LINE_AA,
        )
    return img
