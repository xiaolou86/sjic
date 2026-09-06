#!/bin/bash

# 启动 nginx
nginx

# 数据库迁移
cd /app/backend
export FLASK_APP=run.py
flask db upgrade

# 启动后端 - 使用 run.py
python run.py 