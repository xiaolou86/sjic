#!/bin/bash
# 在管理平台服务器上执行一次：准备 /opt/sjic，挂载应用目录并启动升级器。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行，以便安装 systemd 服务并访问 Docker。" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT=/opt/sjic
DEST="$ROOT/releases/initial"

if ! docker image inspect sjic-backend:runtime >/dev/null 2>&1 || ! docker image inspect sjic-frontend:runtime >/dev/null 2>&1; then
  echo "缺少运行时镜像。请先在仓库根目录执行: docker compose build" >&2
  exit 1
fi
if [ ! -d "$REPO/frontend/build" ]; then
  echo "缺少 frontend/build。请先在 frontend 目录执行 npm run build。" >&2
  exit 1
fi

mkdir -p "$ROOT/updater" "$ROOT/incoming" "$ROOT/releases" \
  "$ROOT/data/instance" "$ROOT/data/data" "$ROOT/data/alerts" "$ROOT/data/models" \
  "$ROOT/data/videos" "$ROOT/data/logs" "$ROOT/data/branding" "$ROOT/data/upgrades"

install_file() {
  local src="$1"
  local dest="$2"
  sed 's/\r$//' "$src" > "$dest"
  chmod 755 "$dest"
}

install_file "$REPO/deploy/verify_release.py" "$ROOT/updater/verify_release.py"
install_file "$SCRIPT_DIR/sjic-updater.sh" "$ROOT/updater/sjic-updater.sh"
install_file "$SCRIPT_DIR/docker-compose.yml" "$ROOT/updater/docker-compose.yml"
chmod 644 "$ROOT/updater/verify_release.py" "$ROOT/updater/docker-compose.yml"

if [ ! -L "$ROOT/current" ]; then
  rm -rf "$DEST"
  mkdir -p "$DEST/backend" "$DEST/frontend"
  cp -a "$REPO/backend"/. "$DEST/backend"/
  rm -rf "$DEST/backend/instance" "$DEST/backend/__pycache__" "$DEST/backend/tests" "$DEST/backend/logs"
  cp -a "$REPO/frontend/build" "$DEST/frontend/build"
  printf '1.0.0\n' > "$DEST/VERSION"
  printf '1.0.0\n' > "$DEST/backend/VERSION"
  ln -sfn "$DEST" "$ROOT/current"
fi

docker compose -f "$ROOT/updater/docker-compose.yml" up -d
for _ in $(seq 1 30); do
  if docker exec sjic-backend python -c 'print(1)' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec -e SJIC_MIGRATE_ONLY=1 sjic-backend python -c "import migrate_entry; migrate_entry.main()"

sed 's/\r$//' "$SCRIPT_DIR/sjic-updater.service" > /etc/systemd/system/sjic-updater.service
systemctl daemon-reload
systemctl enable --now sjic-updater.service
echo "管理平台已按 /opt/sjic/current 挂载启动。之后在页面上传安装包升级。"
