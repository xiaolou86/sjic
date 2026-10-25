#!/bin/sh
# 发版目录和镜像里都只有 main.pyc。开发机直接挂源码时仍可跑 main.py。
set -e
cd /app
if [ -f /app/main.pyc ]; then
  exec python /app/main.pyc
fi
exec python /app/main.py
