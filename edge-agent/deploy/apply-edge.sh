#!/bin/bash
# 边缘入口。升级步骤在 apply-package.sh 和安装包内的 install.sh，本文件不要加逻辑。
set -euo pipefail

ROOT="${SJIC_ROOT:-/opt/sjic}"
export SJIC_ROOT="$ROOT"
export SJIC_COMPONENT=edge
exec bash "$ROOT/updater/apply-package.sh" "$@"
