# 边缘 Agent 镜像
# Jetson 默认基于 Ultralytics JetPack6 镜像（已含 CUDA / ultralytics / torch）
# 构建示例见同目录 docker-compose.yml

ARG BASE_IMAGE=ultralytics/ultralytics:latest-jetson-jetpack6
FROM ${BASE_IMAGE}

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    TZ=Asia/Shanghai

# RTSP 硬解：pip 的 opencv-python-headless 不带 GStreamer，utils/stream.py 经 PyGObject 直接跑
# GStreamer 管道（nvv4l2decoder 来自 L4T，不在这里装；缺了就回退 FFmpeg 软解）。
# apt 的 python3-gi 只装给系统 Python；python:3.10-slim 里用不上，x86 构建传 0。
ARG INSTALL_GSTREAMER=1
RUN if [ "${INSTALL_GSTREAMER}" = "1" ]; then \
        apt-get update && \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
            gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
            gstreamer1.0-plugins-bad gstreamer1.0-libav && \
        rm -rf /var/lib/apt/lists/*; \
    fi

# 仅安装 Agent 通用依赖；推理框架由基础镜像提供（Jetson）
# x86 构建时请通过 build-args 换成带 torch 的 requirements
ARG REQUIREMENTS_FILE=requirements.txt
COPY requirements.txt requirements-cpu.txt requirements-jetson.txt ./
RUN pip install --no-cache-dir -r "${REQUIREMENTS_FILE}"

COPY . .

# 客户镜像不留 .py。字节码用本镜像里的解释器编译，和现场一致。
# 升级包会整目录挂到 /app，盖住这里的文件；入口脚本随升级包一起换。
RUN python -m compileall -b -f -q /app \
    && find /app -depth -type d -name __pycache__ -exec rm -rf {} + \
    && find /app -type f -name '*.py' -delete \
    && sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /app/models /app/alerts /app/logs

CMD ["/bin/sh", "/app/entrypoint.sh"]
