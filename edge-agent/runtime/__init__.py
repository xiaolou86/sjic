"""
推理后端工厂
根据 config.yaml 中的 architecture 字段，自动创建对应平台的推理引擎实例。
"""
from .base_runtime import BaseRuntime, DetectionResult, DetectionBox
import logging

logger = logging.getLogger('runtime')


def create_runtime(architecture: str) -> BaseRuntime:
    """
    推理后端工厂函数。
    
    :param architecture: 平台标识，来自 config.yaml 的 architecture 字段
        - 'jetson'       → UltralyticsRuntime (NVIDIA TensorRT/CUDA)
        - 'x86'          → UltralyticsRuntime (CUDA/CPU)
        - 'moore_e1000'  → MusaRuntime        (torch_musa)
        - 'rk3588'       → RKNNRuntime        (rknn-toolkit2)
    :return: BaseRuntime 子类实例
    """
    arch = architecture.lower().strip()

    if arch in ('jetson', 'x86', 'gpu', 'cpu'):
        from .ultralytics_runtime import UltralyticsRuntime
        logger.info(f"Creating UltralyticsRuntime for architecture: {arch}")
        return UltralyticsRuntime()

    elif arch == 'moore_e1000':
        from .musa_runtime import MusaRuntime
        logger.info(f"Creating MusaRuntime for architecture: {arch}")
        return MusaRuntime()

    elif arch == 'rk3588':
        from .rknn_runtime import RKNNRuntime
        logger.info(f"Creating RKNNRuntime for architecture: {arch}")
        return RKNNRuntime()

    else:
        raise ValueError(
            f"Unsupported architecture: '{architecture}'. "
            f"Supported: jetson, x86, moore_e1000, rk3588"
        )
