# Jetson 初次部署

在 Jetson 上用 Docker Compose 构建并启动 edge-agent。管理平台需已在局域网内运行。

## 环境

- JetPack 6
- Docker，以及 NVIDIA Container Runtime（`docker info` 能看到 `nvidia` runtime）
- 盒子能访问管理平台：MQTT `38883`、API `38881`
- 首次构建需要从外网拉取基础镜像 `ultralytics/ultralytics:latest-jetson-jetpack6`

## 步骤

1. 把 `edge-agent` 目录拷到 Jetson。

2. 编辑同目录 `config.yaml`：

```yaml
architecture: "jetson"

mqtt:
  broker_url: "管理平台IP"
  broker_port: 38883

platform:
  api_base_url: "http://管理平台IP:38881/api/edge"
```

`edge_name` 可留空，此时使用主机名。

3. 在 `edge-agent` 目录启动：

```bash
docker compose up -d --build
```

镜像标签为 `sjic-edge:jetson`，容器名为 `sjic-edge`。基础镜像已含 CUDA、PyTorch、Ultralytics，构建时只再安装 `requirements.txt`。


## 改配置

`config.yaml` 以只读方式挂进容器。改完后执行：

```bash
docker compose restart
```

## 常用命令

```bash
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
```
