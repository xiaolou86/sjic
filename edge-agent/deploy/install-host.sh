#!/bin/bash
# 在 Jetson 上执行一次。先在本目录构建镜像，再挂载 /opt/sjic/current/edge-agent。
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 执行。" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_VERIFY="$(cd "$SCRIPT_DIR/../.." && pwd)/deploy/verify_release.py"
ROOT=/opt/sjic
DEST="$ROOT/releases/initial"

if ! docker image inspect sjic-edge:jetson >/dev/null 2>&1; then
  echo "缺少镜像 sjic-edge:jetson。请先在 edge-agent 目录执行: docker compose build" >&2
  exit 1
fi

VERIFY_SRC="$SCRIPT_DIR/verify_release.py"
if [ -f "$REPO_VERIFY" ]; then
  VERIFY_SRC="$REPO_VERIFY"
fi
if [ ! -f "$VERIFY_SRC" ]; then
  echo "缺少 verify_release.py。请从仓库 deploy/verify_release.py 拷到 edge-agent/deploy/。" >&2
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

install_file "$VERIFY_SRC" "$ROOT/updater/verify_release.py" 644
install_file "$SCRIPT_DIR/apply-edge.sh" "$ROOT/updater/apply-edge.sh" 755
install_file "$SCRIPT_DIR/docker-compose.yml" "$ROOT/updater/docker-compose.yml" 644

if [ ! -f "$ROOT/edge/config.yaml" ]; then
  sed 's/\r$//' "$AGENT_DIR/config.yaml" > "$ROOT/edge/config.yaml"
  echo "已写入 $ROOT/edge/config.yaml。请确认 architecture 为 jetson，并填写平台地址。"
fi

if [ ! -L "$ROOT/current" ]; then
  rm -rf "$DEST"
  mkdir -p "$DEST/edge-agent"
  cp -a "$AGENT_DIR"/. "$DEST/edge-agent"/
  rm -rf "$DEST/edge-agent/deploy" "$DEST/edge-agent/tests" "$DEST/edge-agent/logs" \
    "$DEST/edge-agent/models" "$DEST/edge-agent/alerts" "$DEST/edge-agent/__pycache__"
  rm -f "$DEST/edge-agent/config.yaml"
  if [ ! -f "$DEST/edge-agent/VERSION" ]; then
    printf '1.0.0\n' > "$DEST/edge-agent/VERSION"
  fi
  printf '1.0.0\n' > "$DEST/VERSION"
  ln -sfn "$DEST" "$ROOT/current"
fi

docker compose -f "$ROOT/updater/docker-compose.yml" up -d
echo "Jetson Agent 已按 /opt/sjic/current/edge-agent 挂载启动。之后由管理平台页面下发升级。"
