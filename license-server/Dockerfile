FROM python:3.10-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    LICENSE_DB_PATH=/app/data/licenses.db

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --index-url ${PIP_INDEX_URL} -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 38890

CMD ["gunicorn", "--bind", "0.0.0.0:38890", "--workers", "2", "--access-logfile", "-", "app:create_app()"]
