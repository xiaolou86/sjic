#!/bin/bash
# 校验通过后由宿主机升级器执行；首次安装时由 bundle-install.sh 直接执行。
# 工作目录无关，脚本根据自身位置找到解压后的安装包。
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
INCOMING="$ROOT/incoming"
STATUS_FILE="$INCOMING/${COMPONENT}.status.json"
DB="$ROOT/data/instance/app.db"
BACKUP_DIR="$ROOT/data/instance/backups"
IMAGES_DIR="$ROOT/data/data/images"
EDGE_READY="$INCOMING/edge.ready"
EDGE_JOB="$INCOMING/edge-job"
EDGE_UNIT=sjic-edge-upgrade
BACKUP=""
ROLLBACK_ON_ERROR=0
PREV=""
if [ -L "$ROOT/current" ]; then
  PREV="$(readlink -f "$ROOT/current" || true)"
fi

write_status() {
  local state="$1"
  local message="${2:-}"
  message="${message//\\/\\\\}"
  message="${message//\"/\\\"}"
  mkdir -p "$INCOMING"
  printf '{"state":"%s","version":"%s","message":"%s"}\n' "$state" "$VERSION" "$message" > "$STATUS_FILE"
}

fail() {
  write_status failed "$1"
  echo "$1" >&2
  exit 1
}

require_space() {
  local need_mb="$1"
  local free_mb
  free_mb="$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')"
  if [ -n "$free_mb" ] && [ "$free_mb" -lt "$need_mb" ]; then
    fail "磁盘剩余 ${free_mb} MB，至少需要 ${need_mb} MB，未做任何改动"
  fi
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

# 保留当前版本、上一版和再往前一版。按目录名比较：/opt/sjic 本身可能是软链。
prune_releases() {
  local current previous dir name
  local older=0
  current="$(basename "$(readlink -f "$ROOT/current")")"
  previous="$(basename "${PREV:-none}")"
  while IFS= read -r dir; do
    dir="${dir%/}"
    name="$(basename "$dir")"
    if [ "$name" = "$current" ] || [ "$name" = "$previous" ]; then
      continue
    fi
    older=$((older + 1))
    if [ "$older" -gt 1 ]; then
      rm -rf "$dir"
    fi
  done < <(ls -1dt "$ROOT"/releases/*/ 2>/dev/null || true)
}

# ---------- 平台 ----------

db_size_mb() {
  local total=0
  local file size
  for file in "$DB" "$DB-wal"; do
    if [ -f "$file" ]; then
      size="$(du -m "$file" | cut -f1)"
      total=$((total + size))
    fi
  done
  echo "$total"
}

# 数据库是 WAL 模式，后端停止后要连同 -wal 一起复制，否则会丢最近的写入。
backup_db() {
  if [ ! -f "$DB" ]; then
    return 0
  fi
  BACKUP="$BACKUP_DIR/$(date +%Y%m%d-%H%M%S)-$(basename "${PREV:-none}")"
  mkdir -p "$BACKUP"
  cp -a "$DB" "$BACKUP/app.db"
  if [ -f "$DB-wal" ]; then
    cp -a "$DB-wal" "$BACKUP/app.db-wal"
  fi
}

restore_db() {
  if [ -z "$BACKUP" ]; then
    return 0
  fi
  rm -f "$DB-wal" "$DB-shm"
  cp -a "$BACKUP/app.db" "$DB"
  if [ -f "$BACKUP/app.db-wal" ]; then
    cp -a "$BACKUP/app.db-wal" "$DB-wal"
  fi
}

prune_backups() {
  local dir
  local count=0
  while IFS= read -r dir; do
    count=$((count + 1))
    if [ "$count" -gt 3 ]; then
      rm -rf "${dir%/}"
    fi
  done < <(ls -1dt "$BACKUP_DIR"/*/ 2>/dev/null || true)
}

# 旧版本把标定图片等写在版本目录的 backend/images 里。拷到数据目录，已有的不覆盖；
# 安装包自带的文件（清单里登记过且内容没变）不拷。
copy_legacy_images() {
  local dir src rel hash target
  while IFS= read -r dir; do
    dir="${dir%/}"
    if [ ! -d "$dir/backend/images" ]; then
      continue
    fi
    while IFS= read -r src; do
      rel="${src#"$dir/"}"
      target="$IMAGES_DIR/${src#"$dir/backend/images/"}"
      if [ -e "$target" ]; then
        continue
      fi
      hash="$(sha256sum "$src" | cut -d' ' -f1)"
      if [ -f "$dir/manifest.json" ] && grep -qF "\"path\":\"$rel\",\"sha256\":\"$hash\"" "$dir/manifest.json"; then
        continue
      fi
      mkdir -p "$(dirname "$target")"
      cp -p "$src" "$target"
    done < <(find "$dir/backend/images" -type f)
  done < <(ls -1dt "$ROOT"/releases/*/ 2>/dev/null || true)
}

platform_up() {
  docker compose -f "$COMPOSE" up -d --force-recreate --no-deps backend frontend
}

run_migration() {
  docker compose -f "$COMPOSE" run --rm --no-deps -T -e SJIC_MIGRATE_ONLY=1 backend \
    python -c "import migrate_entry; migrate_entry.main()"
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

rollback_platform() {
  local message="$1"
  ROLLBACK_ON_ERROR=0
  write_status failed "$message"
  docker compose -f "$COMPOSE" stop backend || true
  restore_db || true
  if [ -n "$PREV" ]; then
    ln -sfn "$PREV" "$ROOT/current"
  fi
  platform_up || true
  echo "$message" >&2
  exit 1
}

upgrade_platform() {
  require_space $(($(db_size_mb) + 1024))
  write_status running "正在停止平台"
  if [ -n "$PREV" ] && ! docker compose -f "$COMPOSE" stop backend; then
    docker compose -f "$COMPOSE" start backend || true
    fail "无法停止平台后端，未做任何改动"
  fi
  ROLLBACK_ON_ERROR=1
  backup_db
  copy_legacy_images
  switch_release
  write_status running "正在迁移数据库"
  run_migration || rollback_platform "数据库迁移失败，已退回上一版"
  write_status running "正在启动 ${VERSION}"
  platform_up || rollback_platform "容器未能使用新版本启动，已退回上一版"
  wait_platform || rollback_platform "健康检查未通过，已退回上一版"
  ROLLBACK_ON_ERROR=0
  prune_releases
  prune_backups
}

# ---------- 边缘 ----------

edge_up() {
  docker compose -f "$COMPOSE" up -d --force-recreate --no-deps edge-agent
}

# 新 agent 进入主循环后把自己的版本号写进 ready 文件。
wait_edge() {
  local i
  for i in $(seq 1 90); do
    if [ -f "$EDGE_READY" ] && [ "$(tr -d '[:space:]' < "$EDGE_READY")" = "$VERSION" ]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

rollback_edge() {
  local message="$1"
  ROLLBACK_ON_ERROR=0
  # 先写状态再重建，旧 agent 启动时才能读到失败原因。
  write_status failed "$message"
  if [ -n "$PREV" ]; then
    ln -sfn "$PREV" "$ROOT/current"
    edge_up || true
  fi
  echo "$message" >&2
  exit 1
}

# agent 在容器里调用本脚本，进程属于容器的 cgroup，重建容器时会被一起杀掉。
# 所以把安装文件拷出升级器的临时目录（升级器退出时会删除它），交给宿主机 systemd 执行后立即返回。
detach_edge() {
  if systemctl is-active --quiet "$EDGE_UNIT"; then
    fail "已有升级正在执行"
  fi
  require_space 500
  rm -rf "$EDGE_JOB"
  mkdir -p "$EDGE_JOB"
  cp -a "$HERE"/. "$EDGE_JOB"/
  write_status running "已交给宿主机执行"
  if ! systemd-run --unit="$EDGE_UNIT" --collect --quiet \
      --setenv=SJIC_ROOT="$ROOT" --setenv=SJIC_DETACHED=1 \
      /bin/bash "$EDGE_JOB/install.sh"; then
    fail "无法启动宿主机升级任务"
  fi
}

upgrade_edge() {
  require_space 500
  write_status running "正在切换到 ${VERSION}"
  rm -f "$EDGE_READY"
  ROLLBACK_ON_ERROR=1
  switch_release
  edge_up || rollback_edge "边缘容器未能使用新版本启动，已退回上一版"
  wait_edge || rollback_edge "新版本 3 分钟内没有正常运行，已退回上一版"
  ROLLBACK_ON_ERROR=0
  prune_releases
}

on_exit() {
  local code=$?
  if [ "$code" -ne 0 ] && [ "$ROLLBACK_ON_ERROR" = "1" ]; then
    "rollback_${COMPONENT}" "升级中途出错，已退回上一版"
  fi
}

if [ "$COMPONENT" != "platform" ] && [ "$COMPONENT" != "edge" ]; then
  echo "无法识别的安装包类型" >&2
  exit 1
fi
trap on_exit EXIT

if [ "$COMPONENT" = "platform" ]; then
  upgrade_platform
elif [ "${SJIC_DETACHED:-}" != "1" ] && [ "${SJIC_EDGE_INLINE:-}" != "1" ]; then
  detach_edge
  echo "已交给宿主机执行，查看进度: journalctl -u ${EDGE_UNIT}"
  exit 0
else
  upgrade_edge
fi

write_status success ""
if [ "$HERE" = "$EDGE_JOB" ]; then
  rm -rf "$EDGE_JOB"
fi
echo "upgraded ${COMPONENT} to ${VERSION}"
