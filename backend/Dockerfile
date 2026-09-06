# 使用官方 Python 3.10 基础镜像（轻量管理平台，无 CUDA 依赖）
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 安装系统基础依赖 (ffmpeg 用于视频流处理，libgl1/libglib2.0-0 用于基础图像处理, tzdata 用于时区统一)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    gcc \
    python3-dev \
    tzdata \
    mosquitto \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并升级 pip
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 复制应用代码
COPY . .

# 确保启动脚本换行符为 LF 并赋予执行权限
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# 创建持久化数据和日志目录
RUN mkdir -p instance data alerts models videos logs

# 暴露后端 API 与 WebSocket 端口 (38881) 及 MQTT 端口 (38883)
EXPOSE 38881 38883

# 启动命令：后台拉起 mosquitto，前台运行 Flask
CMD ["/app/entrypoint.sh"]
 