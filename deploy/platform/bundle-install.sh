#!/bin/bash
# 在客户管理平台服务器上执行。工作目录是解压后的交付包，不需要源码。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行。" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=/opt/sjic
VERSION="$(tr -d '[:space:]' < "$HERE/VERSION")"
PKG="$HERE/sjic-platform-${VERSION}.tar.gz"
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

docker load -i "$HERE/images/sjic-backend-runtime.tar"
docker load -i "$HERE/images/sjic-frontend-runtime.tar"
if ! docker image inspect sjic-backend:runtime >/dev/null 2>&1 || ! docker image inspect sjic-frontend:runtime >/dev/null 2>&1; then
  echo "镜像导入后仍找不到 sjic-backend:runtime 或 sjic-frontend:runtime" >&2
  exit 1
fi

mkdir -p "$ROOT/updater" "$ROOT/incoming" "$ROOT/releases" \
  "$ROOT/data/instance" "$ROOT/data/data" "$ROOT/data/alerts" "$ROOT/data/models" \
  "$ROOT/data/videos" "$ROOT/data/logs" "$ROOT/data/branding" "$ROOT/data/upgrades"

install_file() {
  local src="$1"
  local dest="$2"
  local mode="$3"
  sed 's/\r$//' "$src" > "$dest"
  chmod "$mode" "$dest"
}

install_file "$HERE/updater/verify_release.py" "$ROOT/updater/verify_release.py" 644
install_file "$HERE/updater/apply-package.sh" "$ROOT/updater/apply-package.sh" 755
install_file "$HERE/updater/sjic-updater.sh" "$ROOT/updater/sjic-updater.sh" 755
install_file "$HERE/updater/docker-compose.yml" "$ROOT/updater/docker-compose.yml" 644

if [ ! -L "$ROOT/current" ]; then
  STAGING="$(mktemp -d "$ROOT/incoming/staging.XXXXXX")"
  tar -xzf "$PKG" -C "$STAGING"
  SJIC_ROOT="$ROOT" bash "$STAGING/install.sh"
  echo "管理平台 ${VERSION} 已启动。浏览器打开 http://<本机IP>:38880"
else
  echo "已存在 /opt/sjic/current，不覆盖应用和数据。已导入镜像并更新升级器，正在重建容器。"
  docker compose -f "$ROOT/updater/docker-compose.yml" up -d --force-recreate
  echo "容器已按现有应用重建。当前应用版本见 $ROOT/current/VERSION。"
fi

install_file "$HERE/updater/sjic-updater.service" /etc/systemd/system/sjic-updater.service 644
systemctl daemon-reload
systemctl enable sjic-updater.service
systemctl restart sjic-updater.service
