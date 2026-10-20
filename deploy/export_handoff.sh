#!/bin/bash
# 在 Linux 打包机上把镜像和应用包组装成交接运维的交付包。不要在客户环境执行。
set -euo pipefail

VERSION=""
COMPONENT="all"
EDGE_IMAGE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --component) COMPONENT="${2:-}"; shift 2 ;;
    --edge-image) EDGE_IMAGE="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$VERSION" ]; then
  echo "请指定 --version，例如: bash deploy/export_handoff.sh --version 1.0.0 --edge-image /path/sjic-edge-jetson.tar" >&2
  exit 1
fi
case "$COMPONENT" in
  platform|edge|all) ;;
  *) echo "--component 只能是 platform、edge 或 all" >&2; exit 1 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/dist/.handoff-staging"
mkdir -p "$STAGING"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

image_exists() {
  docker image inspect "$1" >/dev/null 2>&1
}

read_package() {
  local path="$1"
  local component="$2"
  local version="$3"
  local manifest got_component got_version
  if [ ! -f "$path" ]; then
    echo "缺少 $path。请先执行: SJIC_VERSION=$version docker compose -f deploy/docker-compose.pack.yml run --rm pack" >&2
    exit 1
  fi
  manifest="$(tar -xOf "$path" manifest.json)"
  got_component="$(printf '%s' "$manifest" | sed -n 's/.*"component"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  got_version="$(printf '%s' "$manifest" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ "$got_component" != "$component" ] || [ "$got_version" != "$version" ]; then
    echo "$(basename "$path") 是 ${got_component} ${got_version}，与本次要导出的 ${component} ${version} 不一致。" >&2
    exit 1
  fi
}

copy_lf() {
  mkdir -p "$(dirname "$2")"
  sed 's/\r$//' "$1" > "$2"
}

archive_dir() {
  local folder="$1"
  local dest="$2"
  rm -f "$dest"
  tar -czf "$dest" -C "$(dirname "$folder")" "$(basename "$folder")"
  echo "$dest"
}

export_platform() {
  local package="$REPO/dist/sjic-platform-${VERSION}.tar.gz"
  local folder="$STAGING/sjic-platform-setup-${VERSION}"
  read_package "$package" platform "$VERSION"
  image_exists sjic-backend:runtime || { echo "开发机上没有镜像 sjic-backend:runtime。请先执行: docker compose build" >&2; exit 1; }
  image_exists sjic-frontend:runtime || { echo "开发机上没有镜像 sjic-frontend:runtime。请先执行: docker compose build" >&2; exit 1; }
  rm -rf "$folder"
  mkdir -p "$folder/images" "$folder/updater"
  docker save -o "$folder/images/sjic-backend-runtime.tar" sjic-backend:runtime
  docker save -o "$folder/images/sjic-frontend-runtime.tar" sjic-frontend:runtime
  cp -a "$package" "$folder/"
  copy_lf "$REPO/deploy/platform/bundle-install.sh" "$folder/install.sh"
  copy_lf "$REPO/deploy/verify_release.py" "$folder/updater/verify_release.py"
  copy_lf "$REPO/deploy/platform/sjic-updater.sh" "$folder/updater/sjic-updater.sh"
  copy_lf "$REPO/deploy/platform/sjic-updater.service" "$folder/updater/sjic-updater.service"
  copy_lf "$REPO/deploy/platform/docker-compose.yml" "$folder/updater/docker-compose.yml"
  printf '%s\n' "$VERSION" > "$folder/VERSION"
  archive_dir "$folder" "$REPO/dist/sjic-platform-setup-${VERSION}.tar.gz"
  rm -rf "$folder"
}

export_edge() {
  local package="$REPO/dist/sjic-edge-${VERSION}.tar.gz"
  local folder="$STAGING/sjic-edge-setup-${VERSION}"
  read_package "$package" edge "$VERSION"
  rm -rf "$folder"
  mkdir -p "$folder/images" "$folder/updater"
  if [ -n "$EDGE_IMAGE" ]; then
    if [ ! -f "$EDGE_IMAGE" ]; then
      echo "找不到边缘镜像文件 $EDGE_IMAGE" >&2
      exit 1
    fi
    cp -a "$EDGE_IMAGE" "$folder/images/sjic-edge-jetson.tar"
  elif image_exists sjic-edge:jetson; then
    docker save -o "$folder/images/sjic-edge-jetson.tar" sjic-edge:jetson
  else
    echo "开发机上没有 sjic-edge:jetson。请在 Jetson 构建机执行 docker save -o sjic-edge-jetson.tar sjic-edge:jetson，再使用 --edge-image 指定。" >&2
    exit 1
  fi
  cp -a "$package" "$folder/"
  copy_lf "$REPO/edge-agent/deploy/bundle-install.sh" "$folder/install.sh"
  copy_lf "$REPO/edge-agent/config.yaml.example" "$folder/config.yaml.example"
  copy_lf "$REPO/deploy/verify_release.py" "$folder/updater/verify_release.py"
  copy_lf "$REPO/edge-agent/deploy/apply-edge.sh" "$folder/updater/apply-edge.sh"
  copy_lf "$REPO/edge-agent/deploy/docker-compose.yml" "$folder/updater/docker-compose.yml"
  printf '%s\n' "$VERSION" > "$folder/VERSION"
  archive_dir "$folder" "$REPO/dist/sjic-edge-setup-${VERSION}.tar.gz"
  rm -rf "$folder"
}

if [ "$COMPONENT" = "platform" ] || [ "$COMPONENT" = "all" ]; then
  export_platform
fi
if [ "$COMPONENT" = "edge" ] || [ "$COMPONENT" = "all" ]; then
  export_edge
fi
