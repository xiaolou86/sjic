.PHONY: install run test clean init-db frontend backend docker-build docker-up docker-down

# 变量定义
PYTHON = python3.10
PIP = pip3.10
FLASK = flask
VENV = venv
BACKEND_DIR = backend
FRONTEND_DIR = frontend

# 安装依赖
install:
	@echo "Installing backend dependencies..."
	cd $(BACKEND_DIR) && $(PIP) install -r requirements.txt
	@echo "Installing frontend dependencies..."
	cd $(FRONTEND_DIR) && npm install

# 初始化数据库
init-db:
	@echo "Applying database migrations..."
	cd $(BACKEND_DIR) && export FLASK_APP=run.py && $(FLASK) db upgrade

# 数据库迁移
migrate:
	@echo "Running database migrations..."
	cd $(BACKEND_DIR) && export FLASK_APP=run.py && flask db upgrade

# 运行后端开发服务器
backend:
	@echo "Starting backend server..."
	cd $(BACKEND_DIR) && $(PYTHON) run.py

# 运行前端开发服务器
frontend:
	@echo "Starting frontend development server..."
	cd $(FRONTEND_DIR) && npm start

# 运行测试
test:
	@echo "Running backend tests..."
	cd $(BACKEND_DIR) && pytest
	@echo "Running frontend tests..."
	cd $(FRONTEND_DIR) && npm test

# 清理临时文件
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} +
	find . -type d -name "*.egg" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name "node_modules" -exec rm -r {} +
	find . -type d -name "build" -exec rm -r {} +

# Docker 相关命令
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# 创建虚拟环境
venv:
	$(PYTHON) -m venv $(VENV)
	@echo "Virtual environment created. Activate it with 'source venv/bin/activate'"

# 帮助信息
help:
	@echo "Available commands:"
	@echo "  make install      - Install all dependencies"
	@echo "  make init-db      - Initialize the database"
	@echo "  make backend      - Run backend development server"
	@echo "  make frontend     - Run frontend development server"
	@echo "  make test         - Run all tests"
	@echo "  make clean        - Clean temporary files"
	@echo "  make venv         - Create virtual environment"
	@echo "  make docker-build - Build Docker images"
	@echo "  make docker-up    - Start Docker containers"
	@echo "  make docker-down  - Stop Docker containers" 