from .belt_broken import BeltBrokenAlgorithm
# from .object_detection import ObjectDetectionAlgorithm
# from .belt_deviation import BeltDeviationAlgorithm

# 算法注册表：提供给 TaskManager 动态反射调用
ALGORITHM_REGISTRY = {
    "belt_broken": BeltBrokenAlgorithm,
    "belt_broken_rcnn": BeltBrokenAlgorithm, # just aliasing for now as examples
    # "object_detection": ObjectDetectionAlgorithm,
    # "belt_deviation": BeltDeviationAlgorithm,
}

def get_algorithm(algo_type: str):
    """根据类型返回纯算法实例"""
    algo_class = ALGORITHM_REGISTRY.get(algo_type)
    if algo_class:
        return algo_class()
    return None
