#!/bin/bash
# 常驻在管理平台宿主机。业务容器只投放请求文件，由这里校验安装包并执行 install.sh。
set -euo pipefail

ROOT="${SJIC_ROOT:-/opt/sjic}"
INCOMING="$ROOT/incoming"
REQUEST="$INCOMING/platform.request.json"
VERIFY="$ROOT/updater/verify_release.py"
mkdir -p "$INCOMING" "$ROOT/releases" "$ROOT/updater"

read_package() {
  sed -n 's/.*"package"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -1
}

write_status() {
  local state="$1"
  local version="$2"
  local message="$3"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  printf '{"state":"%s","version":"%s","message":"%s"}\n' "$state" "$version" "$message" > "$INCOMING/platform.status.json"
}

CURRENT=""
if [ -f "$ROOT/current/VERSION" ]; then
  CURRENT="$(tr -d '[:space:]' < "$ROOT/current/VERSION")"
fi

while true; do
  if [ -f "$REQUEST" ]; then
    WORK="$INCOMING/platform.request.running"
    mv "$REQUEST" "$WORK"
    PKG="$(read_package "$WORK")"
    STAGING=""
    if [ -z "$PKG" ] || [ ! -f "$PKG" ]; then
      write_status failed "" "找不到安装包"
    elif ! docker exec sjic-backend python "$VERIFY" "$PKG" --current "$CURRENT"; then
      write_status failed "" "安装包校验失败"
    else
      STAGING="$(mktemp -d "$INCOMING/staging.XXXXXX")"
      if tar -xzf "$PKG" -C "$STAGING" && [ -f "$STAGING/install.sh" ]; then
        if SJIC_ROOT="$ROOT" bash "$STAGING/install.sh"; then
          if [ -f "$ROOT/current/VERSION" ]; then
            CURRENT="$(tr -d '[:space:]' < "$ROOT/current/VERSION")"
          fi
        fi
      else
        write_status failed "" "安装包解压失败"
      fi
    fi
    if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
      rm -rf "$STAGING"
    fi
    rm -f "$WORK"
  fi
  sleep 2
done
