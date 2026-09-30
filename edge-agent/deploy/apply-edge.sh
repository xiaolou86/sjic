#!/bin/bash
# 边缘宿主机入口。Agent 通过 nsenter 调用，容器被重建后本脚本仍留在宿主机上。
set -euo pipefail

PKG="${1:?package path}"
EXPECT="${2:-}"
ROOT="${SJIC_ROOT:-/opt/sjic}"
VERIFY="$ROOT/updater/verify_release.py"
INCOMING="$ROOT/incoming"
mkdir -p "$INCOMING"

write_status() {
  local state="$1"
  local message="$2"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  printf '{"state":"%s","version":"","message":"%s"}\n' "$state" "$message" > "$INCOMING/edge.status.json"
}

ARGS=("$VERIFY" "$PKG")
if [ -n "$EXPECT" ]; then
  ARGS+=(--sha256 "$EXPECT")
fi

if ! docker exec sjic-edge python "${ARGS[@]}"; then
  write_status failed "安装包校验失败"
  exit 1
fi

STAGING="$(mktemp -d "$INCOMING/staging.XXXXXX")"
cleanup() {
  rm -rf "$STAGING"
}
trap cleanup EXIT

tar -xzf "$PKG" -C "$STAGING"
if [ ! -f "$STAGING/install.sh" ]; then
  write_status failed "安装包缺少 install.sh"
  exit 1
fi
SJIC_ROOT="$ROOT" bash "$STAGING/install.sh"
