from abc import ABC, abstractmethod
from datetime import datetime
import cv2
import os
from shapely.geometry import Point, Polygon
import numpy as np

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

    def draw_alert_overlay(self, frame, boxes=None, roi_points=None, caption=None):
        """在告警截图上画规则 ROI、检测框和说明文字。"""
        vis = frame.copy()
        if roi_points and len(roi_points) >= 3:
            pts = np.array(roi_points, dtype=np.int32).reshape((-1, 1, 2))
            overlay = vis.copy()
            cv2.fillPoly(overlay, [pts], (0, 255, 255))
            vis = cv2.addWeighted(overlay, 0.18, vis, 0.82, 0)
            cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 255), thickness=2)

        for box in boxes or []:
            x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"cls{getattr(box, 'class_id', 0)}:{float(box.confidence):.2f}"
            vis = _put_text(vis, label, (x1, max(y1 - 22, 4)), color_bgr=(0, 255, 0))
            if hasattr(box, 'foot_center'):
                fx, fy = box.foot_center
                cv2.circle(vis, (int(fx), int(fy)), 4, (0, 0, 255), -1)

        if caption:
            vis = _put_text(vis, caption, (8, 8), color_bgr=(255, 255, 255))
        return vis


_FONT_CACHE = {}


def _load_cjk_font(size=20):
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
        'C:/Windows/Fonts/simhei.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
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
    font = _load_cjk_font(20)
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
                [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2],
                fill=(0, 0, 0, 160),
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
    cv2.putText(
        img, text, (x, y + 16),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1, cv2.LINE_AA,
    )
    return img
