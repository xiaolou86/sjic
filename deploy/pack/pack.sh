#!/bin/sh
# 在打包容器内执行：先构建前端，再用 Python 3.10 打出不含 .py 的安装包。
set -eu

if [ -z "${SJIC_VERSION:-}" ]; then
  echo "请设置版本号，例如：SJIC_VERSION=1.0.1 docker compose -f deploy/docker-compose.pack.yml run --rm pack" >&2
  exit 1
fi

cd /src/frontend
npm ci
npm run build

cd /src
exec python deploy/build_release.py --version "${SJIC_VERSION}" --component "${SJIC_COMPONENT:-all}"
