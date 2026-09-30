# Jetson 初次部署

先构建一次运行时镜像，再把应用目录挂到宿主机。之后的升级不在盒子上重新构建。

## 环境

- JetPack 6
- Docker，以及 NVIDIA Container Runtime（`docker info` 能看到 `nvidia` runtime）
- 盒子能访问管理平台：MQTT `38883`、API `38881`、页面 `38880`
- 首次构建需要从外网拉取基础镜像 `ultralytics/ultralytics:latest-jetson-jetpack6`

把仓库里的 `edge-agent` 和 `deploy` 目录拷到 Jetson（`deploy/verify_release.py` 给宿主机升级器使用）。

## 步骤

1. 在 `edge-agent` 目录编辑 `config.yaml`：

```yaml
architecture: "jetson"

mqtt:
  broker_url: "管理平台IP"
  broker_port: 38883

platform:
  api_base_url: "http://管理平台IP:38881/api/edge"
```

`edge_name` 可留空，此时使用主机名。

2. 构建镜像：

```bash
docker compose build
```

3. 安装宿主机目录并按挂载方式启动：

```bash
sudo bash deploy/install-host.sh
```

脚本会把当前代码放到 `/opt/sjic/releases/initial`，把 `config.yaml` 复制到 `/opt/sjic/edge/config.yaml`（已存在则不覆盖），并启动容器 `sjic-edge`。

4. 看日志：

```bash
docker logs -f sjic-edge
```

出现心跳后，管理平台会按本机 MAC 自动登记该节点。

## 改配置

编辑 `/opt/sjic/edge/config.yaml` 后执行：

```bash
docker restart sjic-edge
```

## 以后升级

在管理平台「系统设置」上传边缘安装包，再在「节点」页对本机选择「升级程序」。不要在盒子上重新 `docker compose build`。
