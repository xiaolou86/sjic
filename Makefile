.PHONY: install run test clean init-db frontend backend docker-build docker-up docker-down release-check package handoff release

# 变量定义
PYTHON = python3.10
PIP = pip3.10
FLASK = flask
VENV = venv
BACKEND_DIR = backend
FRONTEND_DIR = frontend
RELEASE_TAG = $(shell git describe --tags --exact-match --match 'v[0-9]*' HEAD 2>/dev/null)
VERSION = $(patsubst v%,%,$(RELEASE_TAG))
COMPONENT ?= all
EDGE_IMAGE ?= sjic-edge-jetson.tar

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

# Release targets only run from a clean checkout at an exact vX.Y.Z tag.
release-check:
	@test -n "$(RELEASE_TAG)" || { echo "请在正式版本 tag（例如 v1.2.3）对应的提交上运行。" >&2; exit 1; }
	@printf '%s\n' "$(RELEASE_TAG)" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "版本 tag 必须符合 vX.Y.Z，例如 v1.2.3。" >&2; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "工作区必须干净；请先提交或移走未提交的更改。" >&2; exit 1; }

# Build application archives only; useful for routine in-place upgrades.
package: release-check
	SJIC_VERSION="$(VERSION)" SJIC_COMPONENT="$(COMPONENT)" docker compose -f deploy/docker-compose.pack.yml run --rm pack

# Export setup archives from already-built application archives.
handoff: release-check
	bash deploy/export_handoff.sh --version "$(VERSION)" --component "$(COMPONENT)" $(if $(filter all edge,$(COMPONENT)),--edge-image "$(EDGE_IMAGE)")

# Initial delivery: build platform runtime images, package applications, and export setup archives.
release: release-check
	@if [ "$(COMPONENT)" = platform ] || [ "$(COMPONENT)" = all ]; then docker compose build; fi
	SJIC_VERSION="$(VERSION)" SJIC_COMPONENT="$(COMPONENT)" docker compose -f deploy/docker-compose.pack.yml run --rm pack
	bash deploy/export_handoff.sh --version "$(VERSION)" --component "$(COMPONENT)" $(if $(filter all edge,$(COMPONENT)),--edge-image "$(EDGE_IMAGE)")

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
	@echo "  make package      - Package apps from the current vX.Y.Z Git tag"
	@echo "  make release      - Build and export initial setup packages from the current tag"