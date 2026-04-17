"""
RK3588 RKNN 推理后端
适用平台: 瑞芯微 RK3588
依赖: rknn-toolkit2 (rknnlite)
支持模型格式: .rknn

注意: RKNN 的推理输出是原始 numpy tensor，需要手动做后处理（NMS、坐标解码等）。
      此处提供了 YOLOv8 输出格式的标准后处理实现。
"""
from .base_runtime import BaseRuntime, DetectionResult, DetectionBox
import numpy as np
import logging

logger = logging.getLogger('runtime.rknn')

# YOLOv8 RKNN 后处理常量
OBJ_THRESH = 0.45
NMS_THRESH = 0.45


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _nms_boxes(boxes, scores, nms_thresh):
    """标准 NMS 实现"""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        indices = np.where(iou <= nms_thresh)[0]
        order = order[indices + 1]
    return keep


def _postprocess_yolov8(outputs, conf_thresh, imgsz, classes_filter=None):
    """
    YOLOv8 RKNN 输出后处理。
    将 RKNN 的原始 tensor 输出解码为 DetectionBox 列表。
    """
    # YOLOv8 输出形状通常为 (1, 84, 8400) -> 转置为 (8400, 84)
    # 前4列: cx, cy, w, h; 后80列: 类别得分
    if len(outputs) == 0:
        return []

    # 根据 RKNN 导出的具体输出格式可能需要调整
    pred = outputs[0]
    if pred.ndim == 3:
        pred = pred[0]  # 去掉 batch 维度
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T  # 确保形状为 (N, 4+num_classes)

    num_classes = pred.shape[1] - 4
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    class_scores = pred[:, 4:]

    # 转换为 xyxy
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    # 获取每个检测的最大类别得分
    max_scores = np.max(class_scores, axis=1)
    max_classes = np.argmax(class_scores, axis=1)

    # 置信度过滤
    mask = max_scores > conf_thresh
    if classes_filter is not None:
        class_mask = np.isin(max_classes, classes_filter)
        mask = mask & class_mask

    filtered_boxes = np.stack([x1[mask], y1[mask], x2[mask], y2[mask]], axis=1)
    filtered_scores = max_scores[mask]
    filtered_classes = max_classes[mask]

    if len(filtered_boxes) == 0:
        return []

    # NMS
    keep = _nms_boxes(filtered_boxes, filtered_scores, NMS_THRESH)

    result = []
    for idx in keep:
        result.append(DetectionBox(
            x1=int(filtered_boxes[idx][0]),
            y1=int(filtered_boxes[idx][1]),
            x2=int(filtered_boxes[idx][2]),
            y2=int(filtered_boxes[idx][3]),
            confidence=float(filtered_scores[idx]),
            class_id=int(filtered_classes[idx])
        ))
    return result


class RKNNRuntime(BaseRuntime):
    """基于 rknn-toolkit2 的推理后端（RK3588）"""

    def __init__(self):
        self.rknn = None
        self._model_path = None

    def load(self, model_path: str, **kwargs):
        try:
            from rknnlite.api import RKNNLite
        except ImportError:
            raise ImportError(
                "rknnlite not installed. Please install rknn-toolkit2: "
                "pip install rknn-toolkit2"
            )

        self._model_path = model_path
        self.rknn = RKNNLite()

        # 加载 RKNN 模型
        ret = self.rknn.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError(f"Failed to load RKNN model: {model_path}, ret={ret}")

        # 初始化运行环境
        # core_mask: RKNNLite.NPU_CORE_0_1_2 表示使用全部 3 个 NPU 核心
        core_mask = kwargs.get('core_mask', None)
        if core_mask is None:
            try:
                core_mask = RKNNLite.NPU_CORE_0_1_2
            except AttributeError:
                core_mask = 0  # 默认

        ret = self.rknn.init_runtime(core_mask=core_mask)
        if ret != 0:
            raise RuntimeError(f"Failed to init RKNN runtime, ret={ret}")

        logger.info(f"[RKNNRuntime] Model loaded on NPU: {model_path}")

    def infer(self, frame, conf=0.5, classes=None, imgsz=640) -> DetectionResult:
        if self.rknn is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        import cv2
        # RKNN 要求输入尺寸与模型编译时一致
        input_frame = cv2.resize(frame, (imgsz, imgsz))
        # RKNN 期望 RGB 输入
        input_frame = cv2.cvtColor(input_frame, cv2.COLOR_BGR2RGB)

        # 执行推理
        outputs = self.rknn.inference(inputs=[input_frame])

        # 后处理
        boxes = _postprocess_yolov8(outputs, conf, imgsz, classes)

        # 将坐标从 imgsz 缩放回原始帧尺寸
        h_orig, w_orig = frame.shape[:2]
        scale_x = w_orig / imgsz
        scale_y = h_orig / imgsz
        for box in boxes:
            box.x1 = int(box.x1 * scale_x)
            box.y1 = int(box.y1 * scale_y)
            box.x2 = int(box.x2 * scale_x)
            box.y2 = int(box.y2 * scale_y)

        return DetectionResult(boxes=boxes, masks=None)

    def release(self):
        if self.rknn is not None:
            self.rknn.release()
            self.rknn = None
            logger.info("[RKNNRuntime] Released.")
