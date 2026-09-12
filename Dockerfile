# 前端构建阶段
FROM node:22 as frontend-builder

WORKDIR /app/frontend

# 安装前端依赖
COPY frontend/package*.json ./
RUN npm install

# 构建前端
COPY frontend .
RUN npm run build

# 后端构建阶段
FROM python:3.10-slim as backend-builder

WORKDIR /app/backend

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip --default-timeout=1000 install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend .

# 最终运行阶段
FROM python:3.10-slim

ENV TZ=Asia/Shanghai

# 安装运行时依赖和 nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 复制前端构建文件
COPY --from=frontend-builder /app/frontend/build /usr/share/nginx/html

# 复制后端文件和依赖
COPY --from=backend-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=backend-builder /app/backend /app/backend

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

WORKDIR /app/backend

# 环境变量
ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 启动脚本
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 38880 38881

CMD ["/start.sh"]
 
