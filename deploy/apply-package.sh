#!/bin/bash
# 宿主机升级器只做三件事：校验安装包、解压、执行包里的 install.sh。
# 切换版本、数据库迁移、回滚都在安装包的 install.sh 里，随应用包更新，不要写进本文件。
set -euo pipefail

PKG="${1:?package path}"
EXPECT="${2:-}"
ROOT="${SJIC_ROOT:-/opt/sjic}"
COMPONENT="${SJIC_COMPONENT:?platform 或 edge}"
case "$COMPONENT" in
  platform) CONTAINER=sjic-backend ;;
  edge) CONTAINER=sjic-edge ;;
  *) echo "未知组件 $COMPONENT" >&2; exit 1 ;;
esac

INCOMING="$ROOT/incoming"
VERIFY="$ROOT/updater/verify_release.py"
mkdir -p "$INCOMING" "$ROOT/releases"

write_status() {
  local state="$1"
  local message="$2"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  printf '{"state":"%s","version":"","message":"%s"}\n' "$state" "$message" > "$INCOMING/${COMPONENT}.status.json"
}

CURRENT=""
if [ -f "$ROOT/current/VERSION" ]; then
  CURRENT="$(tr -d '[:space:]' < "$ROOT/current/VERSION")"
fi

if [ ! -f "$PKG" ]; then
  write_status failed "找不到安装包"
  exit 1
fi

ARGS=("$VERIFY" "$PKG" --current "$CURRENT")
if [ -n "$EXPECT" ]; then
  ARGS+=(--sha256 "$EXPECT")
fi
if ! docker exec "$CONTAINER" python "${ARGS[@]}"; then
  write_status failed "安装包校验失败"
  exit 1
fi

STAGING="$(mktemp -d "$INCOMING/staging.XXXXXX")"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

if ! tar -xzf "$PKG" -C "$STAGING" || [ ! -f "$STAGING/install.sh" ]; then
  write_status failed "安装包解压失败"
  exit 1
fi
SJIC_ROOT="$ROOT" bash "$STAGING/install.sh"
