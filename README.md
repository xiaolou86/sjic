# 目标检测系统

实时目标检测系统，支持多路视频流和自定义模型训练。

## 功能特点

- 实时视频流检测
- 多模型支持
- 自定义区域告警
- 模型训练功能
- 实时告警记录
- Web 界面配置

## 系统要求

- Python 3.10
- Node.js 16+
- CUDA 11.8+ (推荐用于 GPU 加速)
- Anaconda 或 Miniconda

## 快速开始

### 1. 克隆项目


### 2. 环境配置

使用 PowerShell:

```powershell
# 创建并配置 Conda 环境
.\run.ps1 conda-env

# 激活环境
conda activate detector

# 安装依赖
.\run.ps1 install
```

或使用 CMD:
```cmd
# 创建并配置 Conda 环境
run.bat conda-env

# 激活环境
conda activate detector

# 安装依赖
run.bat install
```

### 3. 初始化数据库

```bash
# PowerShell
.\run.ps1 init-db

# 或 CMD
run.bat init-db
```

### 4. 运行系统

#### 方式一：Docker Compose 一键部署（推荐）

```bash
# 构建并启动后端与前端容器服务
docker compose up -d --build

# 查看容器运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

访问 http://localhost:38880 打开系统界面。

#### 方式二：本地开发环境运行

在第一个终端运行后端：

```bash
# PowerShell
.\run.ps1 backend

# 或 CMD
run.bat backend
```

在第二个终端运行前端：

```bash
# PowerShell
.\run.ps1 frontend

# 或 CMD
run.bat frontend
```

访问 http://localhost:38880 打开系统界面

## 项目结构


```
.
├── backend/                 # 后端代码
│   ├── app/                # Flask 应用
│   │   ├── models/        # 数据模型
│   │   ├── routes/        # API 路由
│   │   ├── services/      # 业务逻辑
│   │   └── utils/         # 工具函数
│   ├── tests/             # 测试代码
│   └── config.py          # 配置文件
├── frontend/              # 前端代码
│   ├── src/              # React 源码
│   │   ├── components/   # 组件
│   │   └── pages/        # 页面
│   └── package.json      # 前端依赖
├── models/               # YOLO 模型文件
├── data/                # 数据存储
├── run.bat              # Windows CMD 运行脚本
├── run.ps1              # Windows PowerShell 运行脚本
└── requirements.txt     # Python 依赖
```

## 主要功能模块

1. **视频源管理**
   - 支持 RTSP/本地摄像头
   - 多路视频流并发处理

2. **检测模型管理**
   - 模型导入/切换
   - 参数配置
   - 自定义训练

3. **区域设置**
   - 自定义检测区域
   - 告警规则配置

4. **告警管理**
   - 实时告警推送
   - 历史记录查询
   - 告警级别设置

## 开发指南

### 后端开发
- Flask + SQLAlchemy
- SocketIO 实时通信
- YOLOv8 目标检测

### 前端开发
- React
- Socket.io-client
- Material-UI 组件库

## 常见问题

1. **conda activate 失败**
   - 确保已安装 Anaconda/Miniconda
   - 使用管理员权限运行终端

2. **CUDA 相关错误**
   - 确认 NVIDIA 驱动已安装
   - 验证 CUDA 版本兼容性

3. **数据库初始化失败**
   - 检查数据库配置
   - 确保有写入权限

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

[许可证类型]

## 联系方式

[联系信息]
