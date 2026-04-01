from .belt_broken import BeltBrokenAlgorithm
from .object_detection import ObjectDetectionAlgorithm
from .belt_deviation_detection import BeltDeviationDetection
from .belt_broken_rcnn import BeltBrokenRCNNAlgorithm
from .belt_broken_series import BeltBrokenSeriesAlgorithm

ALGORITHM_REGISTRY = {
    "belt_broken": BeltBrokenAlgorithm,
    "object_detection": ObjectDetectionAlgorithm,
    "belt_deviation_detection": BeltDeviationDetection,
    "belt_broken_rcnn": BeltBrokenRCNNAlgorithm,
    "belt_broken_series": BeltBrokenSeriesAlgorithm
}

def get_algorithm(algorithm_type):
    """
    边缘端算法工厂分配器
    根据云端平台下发的字典任务，动态实例化并返回具体的干活类
    """
    AlgoClass = ALGORITHM_REGISTRY.get(algorithm_type)
    if AlgoClass is None:
        raise ValueError(f"CRITICAL: 边缘盒子中尚未注册该检测算法: {algorithm_type}。请检查代码包。")
    
    return AlgoClass()
