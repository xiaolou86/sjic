"""现场核对取流：走的是哪个解码后端、按 inferFps 取帧实际能到多少、进程占多少 CPU。

在 edge-agent 容器里（工作目录 /app）运行，摄像头地址换成现场的：
    python -m utils.stream_check "rtsp://user:pass@192.168.1.64/Streaming/Channels/101" --fps 5
"""
import argparse
import logging
import threading
import time

from utils.rtsp import FramePump, InferPacer
from utils.stream import _mask_url, open_rtsp_capture

_HW_PREFIXES = ("gstreamer-nvdec", "gstreamer-mpp", "ffmpeg-hw")


def main(argv=None):
    parser = argparse.ArgumentParser(description="核对 RTSP 解码后端与按 inferFps 取帧的实际速率")
    parser.add_argument("url", help="摄像头 RTSP 地址")
    parser.add_argument("--fps", type=float, default=5.0, help="按这个 inferFps 取帧，默认 5")
    parser.add_argument("--seconds", type=float, default=20.0, help="跑多久，默认 20 秒")
    parser.add_argument("--work-ms", type=float, default=0.0, help="模拟每帧推理耗时（毫秒），默认 0")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("stream_check")

    try:
        import psutil
        proc = psutil.Process()
        proc.cpu_percent(None)
    except Exception:
        proc = None

    try:
        cap = open_rtsp_capture(args.url)
    except Exception as e:
        print(f"打不开 {_mask_url(args.url)}：{e}")
        return 2
    backend = getattr(cap, "backend", type(cap).__name__)

    stop = threading.Event()
    pump = FramePump(cap, stop, args.url, log)
    pump.start()
    pacer = InferPacer(args.fps)
    seq = 0
    frames = 0
    misses = 0
    waits = []
    shape = None
    started = time.monotonic()
    try:
        while pacer.wait(stop) and time.monotonic() - started < args.seconds:
            t0 = time.monotonic()
            frame, seq = pump.get_latest(last_seq=seq, wait_sec=2.0)
            waits.append(time.monotonic() - t0)
            if frame is None:
                misses += 1
                log.warning("2 秒内没拿到新帧")
                continue
            frames += 1
            shape = frame.shape
            if args.work_ms > 0:
                time.sleep(args.work_ms / 1000.0)
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = max(time.monotonic() - started, 1e-6)
        cpu = proc.cpu_percent(None) if proc is not None else None
        pump.release()

    hw = "是" if backend.startswith(_HW_PREFIXES) else "否"
    print()
    print(f"解码后端：{backend}（硬件解码：{hw}）")
    if shape is not None:
        print(f"画面：{shape[1]}x{shape[0]}，{shape[2] if len(shape) > 2 else 1} 通道")
    print(f"取帧：目标 {args.fps:g}fps，实际 {frames / elapsed:.2f}fps（{frames} 帧 / {elapsed:.1f}s，没取到 {misses} 次）")
    if waits:
        print(f"每次取帧等待：平均 {sum(waits) / len(waits) * 1000:.0f}ms，最长 {max(waits) * 1000:.0f}ms")
    if cpu is not None:
        print(f"本进程 CPU：{cpu:.0f}%（100% = 占满 1 个核）")
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
