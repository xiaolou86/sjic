"""
Ultralytics YOLO 推理后端
适用平台: Jetson Orin/Nano (TensorRT), x86 (CUDA/CPU)
支持模型格式: .pt, .engine, .onnx
"""
from .base_runtime import BaseRuntime, DetectionResult, DetectionBox
import logging

logger = logging.getLogger('runtime.ultralytics')


class UltralyticsRuntime(BaseRuntime):
    """基于 ultralytics 的推理后端（Jetson / x86 通用）"""

    def __init__(self):
        self.model = None
        self._model_path = None

    def load(self, model_path: str, **kwargs):
        from ultralytics import YOLO
        self._model_path = model_path
        self.model = YOLO(model_path)
        logger.info(f"[UltralyticsRuntime] Loaded model: {model_path}")

    def infer(self, frame, conf=0.5, classes=None, imgsz=640) -> DetectionResult:
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        kwargs = dict(imgsz=imgsz, verbose=False, conf=conf)
        if classes is not None:
            kwargs['classes'] = classes

        raw_results = self.model(frame, **kwargs)

        # 将 ultralytics 结果转换为统一格式
        boxes = []
        masks_data = None

        if len(raw_results) > 0:
            r = raw_results[0]

            # 提取检测框
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                boxes.append(DetectionBox(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=float(box.conf[0]),
                    class_id=int(box.cls[0])
                ))

            # 提取分割掩码（如果有）
            if hasattr(r, 'masks') and r.masks is not None:
                masks_data = r.masks.data.cpu().numpy()

        return DetectionResult(boxes=boxes, masks=masks_data, _raw=raw_results)

    def release(self):
        self.model = None
        logger.info("[UltralyticsRuntime] Released.")
