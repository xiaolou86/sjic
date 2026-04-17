"""
平台硬件信息采集模块
根据 architecture 返回对应盒子的温度、NPU 占用率等硬件指标。
"""
import logging

logger = logging.getLogger('platforms')


def get_platform_info(architecture: str) -> dict:
    """
    获取特定平台的硬件扩展信息。
    
    :param architecture: 平台标识
    :return: 字典，包含 temperature, npu_usage 等平台特定指标
    """
    arch = architecture.lower().strip()

    if arch == 'jetson':
        return _get_jetson_info()
    elif arch == 'rk3588':
        return _get_rk3588_info()
    elif arch == 'moore_e1000':
        return _get_moore_info()
    else:
        return {"temperature": -1.0}


def _get_jetson_info() -> dict:
    """Jetson: 读取 GPU 温度"""
    info = {"temperature": -1.0}
    try:
        # Jetson 热区通常在 thermal_zone1 (GPU)
        with open('/sys/devices/virtual/thermal/thermal_zone1/temp', 'r') as f:
            info["temperature"] = int(f.read().strip()) / 1000.0
    except Exception:
        try:
            # 回退到 zone0 (CPU)
            with open('/sys/devices/virtual/thermal/thermal_zone0/temp', 'r') as f:
                info["temperature"] = int(f.read().strip()) / 1000.0
        except Exception as e:
            logger.debug(f"Failed to read Jetson temperature: {e}")
    return info


def _get_rk3588_info() -> dict:
    """RK3588: 读取 SoC 温度和 NPU 频率"""
    info = {"temperature": -1.0}
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            info["temperature"] = int(f.read().strip()) / 1000.0
    except Exception as e:
        logger.debug(f"Failed to read RK3588 temperature: {e}")

    # 尝试读取 NPU 频率
    try:
        import glob
        npu_paths = glob.glob('/sys/class/devfreq/*.npu/cur_freq')
        if npu_paths:
            with open(npu_paths[0], 'r') as f:
                info["npu_freq_mhz"] = int(f.read().strip()) / 1000000
    except Exception:
        pass

    return info


def _get_moore_info() -> dict:
    """摩尔 E1000: 读取温度和 MUSA 设备信息"""
    info = {"temperature": -1.0}
    try:
        # 尝试通过 torch_musa 获取设备信息
        import torch
        import torch_musa
        if torch.musa.is_available():
            info["musa_device"] = torch.musa.get_device_name(0)
            # 尝试获取显存使用
            info["musa_mem_used_mb"] = round(torch.musa.memory_allocated(0) / 1024 / 1024, 1)
            info["musa_mem_total_mb"] = round(torch.musa.get_device_properties(0).total_memory / 1024 / 1024, 1)
    except ImportError:
        logger.debug("torch_musa not available for Moore E1000 info.")
    except Exception as e:
        logger.debug(f"Failed to read Moore E1000 info: {e}")

    # 通用 Linux 温度读取
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            info["temperature"] = int(f.read().strip()) / 1000.0
    except Exception:
        pass

    return info
