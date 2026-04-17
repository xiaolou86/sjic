"""
推理后端抽象基类
所有平台特定的推理引擎都必须实现此接口，以屏蔽硬件差异。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import cv2


@dataclass
class DetectionBox:
    """单个检测框"""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int

    @property
    def foot_center(self):
        """人体脚部中心点（用于 ROI 判定）"""
        return ((self.x1 + self.x2) // 2, self.y2)

    @property
    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    @property
    def area_px(self):
        return (self.x2 - self.x1) * (self.y2 - self.y1)


@dataclass
class DetectionResult:
    """
    统一的单帧推理结果。
    所有 Runtime 都必须将各自 SDK 的原始输出转换为此格式。
    """
    boxes: List[DetectionBox] = field(default_factory=list)
    masks: Optional[np.ndarray] = None          # 分割掩码 (N, H, W)，可选
    _raw: object = field(default=None, repr=False)  # 原始结果（调试用）

    @property
    def count(self):
        return len(self.boxes)

    def draw_on_frame(self, frame: np.ndarray) -> np.ndarray:
        """在帧上绘制检测结果（通用实现）"""
        vis = frame.copy()
        for box in self.boxes:
            color = (0, 255, 0)
            cv2.rectangle(vis, (box.x1, box.y1), (box.x2, box.y2), color, 2)
            label = f"cls{box.class_id}: {box.confidence:.2f}"
            cv2.putText(vis, label, (box.x1, box.y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return vis


class BaseRuntime(ABC):
    """
    推理后端统一抽象接口。
    每个硬件平台实现自己的子类：
      - UltralyticsRuntime  (Jetson / x86)
      - MusaRuntime          (摩尔 E1000)
      - RKNNRuntime          (RK3588)
    """

    @abstractmethod
    def load(self, model_path: str, **kwargs):
        """
        加载模型文件到推理引擎。
        :param model_path: 本地模型文件路径 (.pt / .engine / .rknn / .mtnn)
        """
        pass

    @abstractmethod
    def infer(self, frame: np.ndarray, conf: float = 0.5,
              classes: list = None, imgsz: int = 640) -> DetectionResult:
        """
        对单帧执行推理。
        :param frame: BGR numpy 数组 (H, W, 3)
        :param conf: 置信度阈值
        :param classes: 过滤的类别 ID 列表，None 表示不过滤
        :param imgsz: 推理输入尺寸
        :return: 统一格式的 DetectionResult
        """
        pass

    @abstractmethod
    def release(self):
        """释放推理资源（GPU 显存、NPU 句柄等）"""
        pass

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass
