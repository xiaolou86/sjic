#!/bin/bash
# 只轮询升级请求，然后调用 apply-package.sh。不要在这里加迁移或回滚。
set -euo pipefail

ROOT="${SJIC_ROOT:-/opt/sjic}"
INCOMING="$ROOT/incoming"
REQUEST="$INCOMING/platform.request.json"
APPLY="$ROOT/updater/apply-package.sh"
mkdir -p "$INCOMING" "$ROOT/releases" "$ROOT/updater"

read_package() {
  local line
  line="$(sed -n 's/.*"package"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1")"
  printf '%s' "${line%%$'\n'*}"
}

while true; do
  if [ -f "$REQUEST" ]; then
    WORK="$INCOMING/platform.request.running"
    mv "$REQUEST" "$WORK"
    PKG="$(read_package "$WORK")"
    SJIC_ROOT="$ROOT" SJIC_COMPONENT=platform bash "$APPLY" "$PKG" || true
    rm -f "$WORK"
  fi
  sleep 2
done
