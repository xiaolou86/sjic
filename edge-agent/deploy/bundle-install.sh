#!/bin/bash
# 在客户 Jetson 上执行。工作目录是解压后的交付包，不需要源码。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行。" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=/opt/sjic
VERSION="$(tr -d '[:space:]' < "$HERE/VERSION")"
PKG="$HERE/sjic-edge-${VERSION}.tar.gz"
IMAGE_TAR="$HERE/images/sjic-edge-jetson.tar"
STAGING=""

cleanup() {
  if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
    rm -rf "$STAGING"
  fi
}
trap cleanup EXIT

if [ ! -f "$PKG" ]; then
  echo "缺少 $PKG" >&2
  exit 1
fi

if [ -f "$IMAGE_TAR" ]; then
  docker load -i "$IMAGE_TAR"
fi
if ! docker image inspect sjic-edge:jetson >/dev/null 2>&1; then
  echo "缺少镜像 sjic-edge:jetson。请把构建机导出的 sjic-edge-jetson.tar 放到 images/ 后重试。" >&2
  exit 1
fi

mkdir -p "$ROOT/updater" "$ROOT/incoming" "$ROOT/releases" \
  "$ROOT/edge/models" "$ROOT/edge/alerts" "$ROOT/edge/logs"

install_file() {
  local src="$1"
  local dest="$2"
  local mode="$3"
  sed 's/\r$//' "$src" > "$dest"
  chmod "$mode" "$dest"
}

install_file "$HERE/updater/verify_release.py" "$ROOT/updater/verify_release.py" 644
install_file "$HERE/updater/apply-package.sh" "$ROOT/updater/apply-package.sh" 755
install_file "$HERE/updater/apply-edge.sh" "$ROOT/updater/apply-edge.sh" 755
install_file "$HERE/updater/docker-compose.yml" "$ROOT/updater/docker-compose.yml" 644

if [ ! -f "$ROOT/edge/config.yaml" ]; then
  sed 's/\r$//' "$HERE/config.yaml.example" > "$ROOT/edge/config.yaml"
  echo "已写入 $ROOT/edge/config.yaml"
fi

if [ ! -L "$ROOT/current" ]; then
  STAGING="$(mktemp -d "$ROOT/incoming/staging.XXXXXX")"
  tar -xzf "$PKG" -C "$STAGING"
  SJIC_ROOT="$ROOT" bash "$STAGING/install.sh"
  echo "边缘 ${VERSION} 已启动。平台地址在 $ROOT/edge/config.yaml，修改后执行: docker restart sjic-edge"
else
  echo "已存在 /opt/sjic/current，不覆盖应用和配置。已导入镜像并更新升级器，正在重建容器。"
  docker compose -f "$ROOT/updater/docker-compose.yml" up -d --force-recreate
  echo "容器已按现有应用重建。当前应用版本见 $ROOT/current/VERSION。平台地址在 $ROOT/edge/config.yaml。"
fi
