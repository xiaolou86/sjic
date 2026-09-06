#!/bin/bash
set -e

echo "[INIT] Starting Mosquitto MQTT broker in background..."
mosquitto -d -c /app/mosquitto.conf

# 等待一小会儿确保 38883 端口就绪
sleep 1

# 修复已上传模型权限，供 frontend nginx（非 root）读取共享卷 ./models
if [ -d /app/models ]; then
  chmod -R a+rX /app/models || true
  echo "[INIT] Ensured /app/models is world-readable for model-nginx sharing"
fi

echo "[INIT] Mosquitto started on port 38883. Starting Flask application..."
exec python run.py
