from .belt_broken import BeltBrokenAlgorithm
from .object_detection import ObjectDetectionAlgorithm
from .belt_deviation_detection import BeltDeviationDetection
from .belt_broken_rcnn import BeltBrokenRCNNAlgorithm
from .belt_broken_series import BeltBrokenSeriesAlgorithm
from .camera_health import CameraHealthAlgorithm
from .pose_behavior import PoseBehaviorAlgorithm
from .mouse_idle import MouseIdleAlgorithm

# 引擎注册表：云端下发 algorithm_type = Algorithm.engine
ALGORITHM_REGISTRY = {
    "belt_broken": BeltBrokenAlgorithm,
    "object_detection": ObjectDetectionAlgorithm,
    "belt_deviation_detection": BeltDeviationDetection,
    "belt_broken_high": BeltBrokenRCNNAlgorithm,
    "belt_broken_series": BeltBrokenSeriesAlgorithm,
    "camera_health": CameraHealthAlgorithm,
    "pose_behavior": PoseBehaviorAlgorithm,
    "mouse_idle": MouseIdleAlgorithm,
}

# 无需下载模型即可启动的引擎
NO_MODEL_ENGINES = frozenset({"camera_health", "mouse_idle"})


def get_algorithm(algorithm_type):
    """
    边缘端算法工厂：按引擎类型实例化。
    """
    AlgoClass = ALGORITHM_REGISTRY.get(algorithm_type)
    if AlgoClass is None:
        raise ValueError(
            f"CRITICAL: 边缘盒子中尚未注册该检测引擎: {algorithm_type}。"
            f"已支持: {sorted(ALGORITHM_REGISTRY.keys())}"
        )
    return AlgoClass()
