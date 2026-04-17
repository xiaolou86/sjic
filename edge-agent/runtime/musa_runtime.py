"""
摩尔 E1000 (MUSA) 推理后端
适用平台: 摩尔线程 E1000 ARM64 NPU
依赖: torch, torch_musa, ultralytics
支持模型格式: .pt (通过 torch_musa 加速), .mtnn (待原厂 SDK 完善后扩展)

原理: torch_musa 为 PyTorch 注册了 "musa" 设备后端，
      ultralytics YOLO 的 model.predict(device='musa') 可直接走 MUSA 加速。
"""
from .base_runtime import BaseRuntime, DetectionResult, DetectionBox
import logging

logger = logging.getLogger('runtime.musa')


class MusaRuntime(BaseRuntime):
    """基于 torch_musa + ultralytics 的推理后端（摩尔 E1000）"""

    def __init__(self):
        self.model = None
        self._model_path = None
        self._musa_available = False
        self._init_musa()

    def _init_musa(self):
        """检测 MUSA 环境是否可用，若不可用直接报错"""
        try:
            import torch
            import torch_musa
            if torch.musa.is_available():
                logger.info(f"[MusaRuntime] MUSA device detected: {torch.musa.get_device_name(0)}")
                self._musa_available = True
            else:
                raise RuntimeError("MUSA device found but is_available() is False. Please check MTHREADS driver.")
        except ImportError as e:
            raise ImportError(f"torch_musa not installed: {e}. Cannot run Moore E1000 platform without it.")
        except Exception as e:
            raise RuntimeError(f"MUSA initialization failed: {e}")

    def load(self, model_path: str, **kwargs):
        from ultralytics import YOLO
        import torch
        self._model_path = model_path
        self.model = YOLO(model_path)

        # 强制将模型迁移到 MUSA 设备，若失败会在此报错
        self.model.to('musa')
        logger.info(f"[MusaRuntime] Model loaded on MUSA device: {model_path}")

    def infer(self, frame, conf=0.5, classes=None, imgsz=640) -> DetectionResult:
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # 强制使用 musa 设备进行推理
        kwargs = dict(imgsz=imgsz, verbose=False, conf=conf, device='musa')
        if classes is not None:
            kwargs['classes'] = classes

        raw_results = self.model(frame, **kwargs)

        # 转换为统一格式（与 UltralyticsRuntime 逻辑一致）
        boxes = []
        masks_data = None

        if len(raw_results) > 0:
            r = raw_results[0]
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                boxes.append(DetectionBox(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=float(box.conf[0]),
                    class_id=int(box.cls[0])
                ))
            if hasattr(r, 'masks') and r.masks is not None:
                masks_data = r.masks.data.cpu().numpy()

        return DetectionResult(boxes=boxes, masks=masks_data, _raw=raw_results)

    def release(self):
        self.model = None
        logger.info("[MusaRuntime] Released.")
