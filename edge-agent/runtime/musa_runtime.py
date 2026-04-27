"""
摩尔 E1000 (MUSA/MTNN) 推理后端
适用平台: 摩尔线程 E1000 ARM64 NPU
支持模型格式: .mtnn (通过 mtnn_api 推理)

说明: 
本后端专为摩尔线程 NPU 设计，直接调用官方 mtnn_api 执行推理。
"""
from .base_runtime import BaseRuntime, DetectionResult, DetectionBox
import numpy as np
import cv2
import time
import logging

logger = logging.getLogger('runtime.musa')

def xywh2xyxy(x):
    """(x, y, w, h) -> (x1, y1, x2, y2)"""
    y = np.copy(x)
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y

def compute_iou(box, boxes):
    """计算单个 box 与一组 boxes 的 IoU"""
    xmin = np.maximum(box[0], boxes[:, 0])
    ymin = np.maximum(box[1], boxes[:, 1])
    xmax = np.minimum(box[2], boxes[:, 2])
    ymax = np.minimum(box[3], boxes[:, 3])
    intersection_area = np.maximum(0, xmax - xmin) * np.maximum(0, ymax - ymin)
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    boxes_area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union_area = box_area + boxes_area - intersection_area
    return intersection_area / union_area

def nms(boxes, scores, iou_threshold):
    """非极大值抑制 (NMS)"""
    sorted_indices = np.argsort(scores)[::-1]
    keep_boxes = []
    while sorted_indices.size > 0:
        box_id = sorted_indices[0]
        keep_boxes.append(box_id)
        ious = compute_iou(boxes[box_id, :], boxes[sorted_indices[1:], :])
        keep_indices = np.where(ious < iou_threshold)[0]
        sorted_indices = sorted_indices[keep_indices + 1]
    return keep_boxes


class MusaRuntime(BaseRuntime):
    """纯 NPU 推理后端"""

    def __init__(self):
        self.session = None
        self._model_path = None
        self.input_width = 640
        self.input_height = 640

    def load(self, model_path: str, **kwargs):
        self._model_path = model_path
        
        try:
            # 只支持加载摩尔官方 mtnn 模型
            import mtnn_api
            logger.info(f"[MusaRuntime] Loading MTNN model via mtnn_api: {model_path}")
            self.session = mtnn_api.MTNNSession(model_path)
        except ImportError as e:
            raise ImportError(f"mtnn_api not found. Please install Moore Threads SDK: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MTNN session: {e}")

    def _letterbox(self, img, target_size=640):
        """
        Letterbox 预处理：等比缩放 + 灰色填充，保持原始宽高比不变。
        与 ultralytics 内部预处理方式一致，避免拉伸变形导致检测框位置偏移。
        
        :return: (padded_img, ratio, pad_w, pad_h)
        """
        h, w = img.shape[:2]
        ratio = min(target_size / h, target_size / w)
        new_w, new_h = int(round(w * ratio)), int(round(h * ratio))

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        dw = target_size - new_w
        dh = target_size - new_h
        pad_w = dw / 2.0
        pad_h = dh / 2.0

        left = int(round(pad_w - 0.1))
        right = int(round(pad_w + 0.1))
        top = int(round(pad_h - 0.1))
        bottom = int(round(pad_h + 0.1))

        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        return padded, ratio, pad_w, pad_h

    def infer(self, frame, conf=0.5, classes=None, imgsz=640) -> DetectionResult:
        if self.session is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # 1. Letterbox 预处理（等比缩放 + 灰边填充，保持宽高比）
        h_orig, w_orig = frame.shape[:2]
        letterboxed, ratio, pad_w, pad_h = self._letterbox(frame, target_size=imgsz)

        input_img = cv2.cvtColor(letterboxed, cv2.COLOR_BGR2RGB)
        input_img = input_img / 255.0
        input_img = input_img.transpose(2, 0, 1)
        input_tensor = input_img[np.newaxis, :, :, :].astype(np.float32)

        # 2. 推理 (MTNN 官方 Session 运行方式)
        start_time = time.perf_counter()
        outputs = self.session.run({0: input_tensor})
        latency = (time.perf_counter() - start_time) * 1000
        logger.debug(f"[MusaRuntime] NPU Inference latency: {latency:.2f} ms")

        # 3. 后处理 (针对 YOLOv8 输出格式 [1, 84, 8400])
        output = outputs[0]
        predictions = np.squeeze(output)
        # 兼容两种常见导出形状:
        # - (84, 8400): 需转置
        # - (8400, 84): 无需转置
        if predictions.ndim == 3:
            predictions = predictions[0]
        if predictions.ndim != 2:
            logger.warning(f"[MusaRuntime] Unexpected output shape: {predictions.shape}")
            return DetectionResult(boxes=[])
        if predictions.shape[0] < predictions.shape[1]:
            predictions = predictions.T
        
        boxes = predictions[:, :4]    # (cx, cy, w, h) 在 640x640 letterbox 空间
        scores = predictions[:, 4:]   # 各类别概率
        
        max_scores = np.max(scores, axis=1)
        
        # 应用置信度阈值
        valid_indices = max_scores > conf
        
        # 类别过滤
        if classes is not None:
            max_classes = np.argmax(scores, axis=1)
            class_indices = np.isin(max_classes, classes)
            valid_indices = valid_indices & class_indices
            
        if not np.any(valid_indices):
            return DetectionResult(boxes=[])
            
        valid_boxes = boxes[valid_indices]
        valid_scores = max_scores[valid_indices]
        valid_class_ids = np.argmax(scores[valid_indices], axis=1)
        
        # xywh 转 xyxy（仍在 640x640 letterbox 空间）
        valid_boxes = xywh2xyxy(valid_boxes)
        
        # ★ 关键修复：逆向还原坐标到原始帧尺寸 ★
        # 第一步：减去灰边偏移量（从 letterbox 空间 → 缩放后的有效区域）
        valid_boxes[:, [0, 2]] -= pad_w
        valid_boxes[:, [1, 3]] -= pad_h
        # 第二步：除以缩放比（从缩放空间 → 原始帧像素坐标）
        valid_boxes /= ratio
        
        # NMS 过滤
        keep = nms(valid_boxes, valid_scores, iou_threshold=0.45)
        
        # 封装结果（坐标已在原始帧空间，可直接绘制）
        final_boxes = []
        for idx in keep:
            final_boxes.append(DetectionBox(
                x1=int(np.clip(valid_boxes[idx][0], 0, w_orig)),
                y1=int(np.clip(valid_boxes[idx][1], 0, h_orig)),
                x2=int(np.clip(valid_boxes[idx][2], 0, w_orig)),
                y2=int(np.clip(valid_boxes[idx][3], 0, h_orig)),
                confidence=float(valid_scores[idx]),
                class_id=int(valid_class_ids[idx])
            ))
            
        return DetectionResult(boxes=final_boxes)

    def release(self):
        self.session = None
        logger.info("[MusaRuntime] MTNN Session released.")
