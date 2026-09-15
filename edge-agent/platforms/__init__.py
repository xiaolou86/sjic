"""
平台硬件信息采集：温度、GPU/NPU 占用等。
未知架构不再抛错，尽量返回已有指标。
GPU/NPU 占用在后台按秒采样，上报近一段时间的平均值，避免瞬时尖峰。
"""
import glob
import logging
import os
import subprocess
import threading
import time
from collections import deque

logger = logging.getLogger('platforms')

GPU_AVG_WINDOW_SEC = 30
GPU_SAMPLE_INTERVAL_SEC = 1.0

_gpu_samples = deque()
_gpu_lock = threading.Lock()
_gpu_sampler_started = False


def start_gpu_sampler(architecture: str):
    """后台按秒采集 GPU/NPU，供心跳上报平均值。"""
    global _gpu_sampler_started
    if _gpu_sampler_started:
        return
    _gpu_sampler_started = True

    def _loop():
        while True:
            try:
                value = _read_gpu_usage_instant(architecture)
                now = time.time()
                with _gpu_lock:
                    if value is not None:
                        _gpu_samples.append((now, float(value)))
                    cutoff = now - GPU_AVG_WINDOW_SEC
                    while _gpu_samples and _gpu_samples[0][0] < cutoff:
                        _gpu_samples.popleft()
            except Exception as e:
                logger.debug(f"gpu sample failed: {e}")
            time.sleep(GPU_SAMPLE_INTERVAL_SEC)

    threading.Thread(target=_loop, name="gpu-sampler", daemon=True).start()


def get_gpu_usage_avg():
    with _gpu_lock:
        vals = [v for _, v in _gpu_samples]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def get_platform_info(architecture: str) -> dict:
    """返回 temperature / gpu_usage / npu_usage 等，缺项则省略。"""
    arch = (architecture or '').lower().strip()
    info = {}
    try:
        if arch.startswith('jetson'):
            info.update(_get_jetson_info())
        elif arch.startswith('rk3588'):
            info.update(_get_rk3588_info())
        elif arch.startswith('moore'):
            info.update(_get_moore_info())
    except Exception as e:
        logger.debug(f"platform info failed for {arch}: {e}")

    instant = _read_gpu_usage_instant(architecture)
    if instant is not None:
        info['gpu_usage'] = instant
        if arch.startswith('rk3588'):
            info['npu_usage'] = instant

    avg = get_gpu_usage_avg()
    if avg is not None:
        info['gpu_usage'] = avg
        info['gpu_usage_window_sec'] = GPU_AVG_WINDOW_SEC
        if arch.startswith('rk3588'):
            info['npu_usage'] = avg

    nv = _get_nvidia_smi_gpu()
    if nv.get('gpu_mem_used_mb') is not None:
        info.setdefault('gpu_mem_used_mb', nv['gpu_mem_used_mb'])
        info.setdefault('gpu_mem_total_mb', nv.get('gpu_mem_total_mb'))
    return info


def _read_gpu_usage_instant(architecture: str):
    arch = (architecture or '').lower().strip()
    if arch.startswith('jetson'):
        value = _get_jetson_gpu_load()
        if value is not None:
            return value
    if arch.startswith('rk3588'):
        value = _get_rknpu_load()
        if value is not None:
            return value
    if arch.startswith('moore'):
        mem_pct = _get_moore_info().get('gpu_usage')
        if mem_pct is not None:
            return mem_pct
    nv = _get_nvidia_smi_gpu()
    if nv.get('gpu_usage') is not None:
        return nv['gpu_usage']
    return _get_jetson_gpu_load()


def _read_int_file(path):
    with open(path, 'r') as f:
        return int(f.read().strip())


def _get_jetson_info() -> dict:
    info = {}
    for zone in ('thermal_zone1', 'thermal_zone0'):
        try:
            info['temperature'] = _read_int_file(f'/sys/devices/virtual/thermal/{zone}/temp') / 1000.0
            break
        except Exception:
            continue
    return info


def _get_jetson_gpu_load():
    candidates = [
        '/sys/devices/gpu.0/load',
        '/sys/devices/platform/gpu.0/load',
        *glob.glob('/sys/devices/platform/*.gpu/load'),
        *glob.glob('/sys/class/devfreq/*.gpu/load'),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            raw = _read_int_file(path)
            # Jetson 常见 0–1000；少数节点直接给 0–100
            return round(raw / 10.0, 1) if raw > 100 else float(raw)
        except Exception:
            continue
    return None


def _get_rk3588_info() -> dict:
    info = {}
    try:
        info['temperature'] = _read_int_file('/sys/class/thermal/thermal_zone0/temp') / 1000.0
    except Exception as e:
        logger.debug(f"Failed to read RK3588 temperature: {e}")

    try:
        npu_paths = glob.glob('/sys/class/devfreq/*.npu/cur_freq')
        if npu_paths:
            info['npu_freq_mhz'] = _read_int_file(npu_paths[0]) / 1000000
    except Exception:
        pass
    return info


def _get_rknpu_load():
    path = '/sys/kernel/debug/rknpu/load'
    if not os.path.exists(path):
        return None
    try:
        text = open(path, 'r').read()
        percents = []
        for token in text.replace('%', ' ').split():
            try:
                percents.append(float(token))
            except ValueError:
                continue
        if percents:
            return round(sum(percents) / len(percents), 1)
    except Exception:
        return None
    return None


def _get_moore_info() -> dict:
    info = {}
    try:
        import torch
        import torch_musa  # noqa: F401
        if torch.musa.is_available():
            info['musa_device'] = torch.musa.get_device_name(0)
            used = torch.musa.memory_allocated(0)
            total = torch.musa.get_device_properties(0).total_memory
            info['musa_mem_used_mb'] = round(used / 1024 / 1024, 1)
            info['musa_mem_total_mb'] = round(total / 1024 / 1024, 1)
            if total:
                info['gpu_usage'] = round(used * 100.0 / total, 1)
    except Exception as e:
        logger.debug(f"Failed to read Moore E1000 info: {e}")

    try:
        info['temperature'] = _read_int_file('/sys/class/thermal/thermal_zone0/temp') / 1000.0
    except Exception:
        pass
    return info


def _get_nvidia_smi_gpu():
    try:
        out = subprocess.check_output(
            [
                'nvidia-smi',
                '--query-gpu=utilization.gpu,memory.used,memory.total',
                '--format=csv,noheader,nounits',
            ],
            timeout=2,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        line = (out or '').strip().split('\n')[0]
        parts = [p.strip() for p in line.split(',') if p.strip() != '']
        if len(parts) < 1:
            return {}
        info = {'gpu_usage': float(parts[0])}
        if len(parts) >= 3:
            info['gpu_mem_used_mb'] = float(parts[1])
            info['gpu_mem_total_mb'] = float(parts[2])
        return info
    except Exception:
        return {}
