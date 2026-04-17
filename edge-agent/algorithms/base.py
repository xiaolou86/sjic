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

    def is_point_in_roi(self, point, points, logger):
        """
        判断点是否在检测区域内
        :param point: 点 (x, y)
        :param points: 检测区域的边界点列表 [(x1, y1), (x2, y2), ..., (xn, yn)]
        :return: bool
        """
        logger.debug(f"Checking if point {point} is in ROI")
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
