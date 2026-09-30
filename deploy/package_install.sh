#!/bin/bash
# 验签通过后由宿主机升级器执行。工作目录无关，脚本根据自身位置找到解压后的安装包。
set -euo pipefail

ROOT="${SJIC_ROOT:-/opt/sjic}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$HERE/manifest.json"
COMPOSE="$ROOT/updater/docker-compose.yml"

json_get() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$MANIFEST" | head -1
}

COMPONENT="$(json_get component)"
VERSION="$(json_get version)"
STATUS_FILE="$ROOT/incoming/${COMPONENT}.status.json"
DB="$ROOT/data/instance/app.db"
DB_BACKUP="$ROOT/data/instance/app.db.bak-${VERSION}"
PREV=""
if [ -L "$ROOT/current" ]; then
  PREV="$(readlink -f "$ROOT/current" || true)"
fi

write_status() {
  local state="$1"
  local message="${2:-}"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  mkdir -p "$ROOT/incoming"
  printf '{"state":"%s","version":"%s","message":"%s"}\n' "$state" "$VERSION" "$message" > "$STATUS_FILE"
}

recreate_platform() {
  docker compose -f "$COMPOSE" up -d --force-recreate --no-deps backend frontend
}

recreate_edge() {
  docker compose -f "$COMPOSE" up -d --force-recreate --no-deps edge-agent
}

rollback_platform() {
  local message="$1"
  if [ -f "$DB_BACKUP" ]; then
    cp -a "$DB_BACKUP" "$DB"
  fi
  if [ -n "$PREV" ]; then
    ln -sfn "$PREV" "$ROOT/current"
    recreate_platform || true
  fi
  write_status failed "$message"
  echo "$message" >&2
  exit 1
}

rollback_edge() {
  local message="$1"
  if [ -n "$PREV" ]; then
    ln -sfn "$PREV" "$ROOT/current"
    recreate_edge || true
  fi
  write_status failed "$message"
  echo "$message" >&2
  exit 1
}

switch_release() {
  local dest="$ROOT/releases/$VERSION"
  local incoming="$ROOT/releases/.${VERSION}.incoming"
  rm -rf "$incoming"
  mkdir -p "$incoming"
  cp -a "$HERE"/. "$incoming"/
  if [ -d "$dest" ] && [ -n "$PREV" ] && [ "$PREV" = "$(readlink -f "$dest")" ]; then
    rm -rf "${dest}.prev"
    mv "$dest" "${dest}.prev"
    PREV="${dest}.prev"
  fi
  rm -rf "$dest"
  mv "$incoming" "$dest"
  ln -sfn "$dest" "$ROOT/current"
}

wait_platform() {
  local i body
  for i in $(seq 1 40); do
    body=$(docker exec sjic-backend python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:38881/api/health", timeout=3).read().decode())' 2>/dev/null) || true
    case "$body" in
      *"\"version\": \"${VERSION}\""*|*"\"version\":\"${VERSION}\""*)
        return 0
        ;;
    esac
    sleep 2
  done
  return 1
}

wait_edge() {
  local i running
  sleep 3
  for i in $(seq 1 20); do
    running="$(docker inspect -f '{{.State.Running}}' sjic-edge 2>/dev/null || echo false)"
    if [ "$running" = "true" ]; then
      sleep 3
      running="$(docker inspect -f '{{.State.Running}}' sjic-edge 2>/dev/null || echo false)"
      if [ "$running" = "true" ]; then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

if [ "$COMPONENT" != "platform" ] && [ "$COMPONENT" != "edge" ]; then
  echo "无法识别的安装包类型" >&2
  exit 1
fi

write_status running "正在切换到 ${VERSION}"
switch_release

if [ "$COMPONENT" = "platform" ]; then
  if [ -f "$DB" ]; then
    cp -a "$DB" "$DB_BACKUP"
  fi
  recreate_platform || rollback_platform "容器未能使用新版本启动"
  if ! docker exec -e SJIC_MIGRATE_ONLY=1 sjic-backend python -c "import migrate_entry; migrate_entry.main()"; then
    rollback_platform "数据库迁移失败，已退回上一版"
  fi
  if ! wait_platform; then
    rollback_platform "健康检查未通过，已退回上一版"
  fi
else
  recreate_edge || rollback_edge "边缘容器未能使用新版本启动"
  if ! wait_edge; then
    rollback_edge "边缘容器启动后退出，已退回上一版"
  fi
fi

write_status success ""
echo "upgraded ${COMPONENT} to ${VERSION}"
