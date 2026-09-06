#!/bin/bash
set -e

echo "[INIT] Starting Mosquitto MQTT broker in background..."
mosquitto -d -c /app/mosquitto.conf

# 等待一小会儿确保 38883 端口就绪
sleep 1

echo "[INIT] Mosquitto started on port 38883. Starting Flask application..."
exec python run.py
