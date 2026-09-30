# 安装包升级

日常升级不重新构建镜像。管理平台和 Jetson 都先执行一次 `install-host.sh`，之后在系统设置页上传安装包。初始版本是 `1.0.0`。

在仓库根目录用打包容器生成安装包，本机不用安装 Python 或 Node。

Linux / macOS：

```bash
SJIC_VERSION=1.0.1 docker compose -f deploy/docker-compose.pack.yml run --rm pack
```

Windows PowerShell：

```powershell
$env:SJIC_VERSION = "1.0.1"
docker compose -f deploy/docker-compose.pack.yml run --rm pack
```

安装包里的 Python 文件只有 `.pyc`。上传时按清单核对每个文件的校验和。

管理平台首次：

```bash
docker compose build
sudo bash deploy/platform/install-host.sh
```

Jetson 首次见 [edge-agent/JETSON_DEPLOY.md](../edge-agent/JETSON_DEPLOY.md)。
