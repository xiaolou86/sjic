#!/bin/bash
# 用桩命令（docker、systemd-run、systemctl、sleep、df）跑 package_install.sh 的主要路径。
# 在 Linux 或 Git Bash 里执行: bash deploy/tests/test_package_install.sh（Windows 需要能创建符号链接）
set -u
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/package_install.sh"
WORK="$(mktemp -d)"
STUB="$WORK/stub"
mkdir -p "$STUB"
export MSYS=winsymlinks:nativestrict
PASS=0
FAIL=0

check() {
  if eval "$2"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $1   [$2]"
  fi
}

cat > "$STUB/docker" <<'EOF'
#!/bin/bash
echo "docker $*" >> "$SJIC_ROOT/docker.log"
case "$*" in
  *" run --rm"*)
    echo "migrated" > "$SJIC_ROOT/data/instance/app.db"
    [ "${FAIL_MIGRATION:-}" = 1 ] && exit 1
    exit 0 ;;
  "exec sjic-backend"*)
    v="$(tr -d '[:space:]' < "$SJIC_ROOT/current/VERSION")"
    echo "{\"status\": \"ok\", \"version\": \"$v\"}"
    exit 0 ;;
  *" up "*edge-agent*)
    if [ "${EDGE_READY:-1}" = 1 ]; then
      tr -d '[:space:]' < "$SJIC_ROOT/current/VERSION" > "$SJIC_ROOT/incoming/edge.ready"
    fi
    exit 0 ;;
esac
exit 0
EOF

cat > "$STUB/systemd-run" <<'EOF'
#!/bin/bash
echo "systemd-run $*" >> "$SJIC_ROOT/systemd.log"
envs=()
while [ $# -gt 0 ]; do
  case "$1" in
    --setenv=*) envs+=("${1#--setenv=}") ;;
    --unit=*|--collect|--quiet) ;;
    *) break ;;
  esac
  shift
done
env "${envs[@]}" "$@"
exit 0
EOF

cat > "$STUB/systemctl" <<'EOF'
#!/bin/bash
[ "${SYSTEMCTL_ACTIVE:-}" = 1 ] && exit 0
exit 3
EOF

cat > "$STUB/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF

cat > "$STUB/df" <<'EOF'
#!/bin/bash
if [ -n "${DF_FREE:-}" ]; then
  printf 'Filesystem 1M-blocks Used Available Capacity Mounted\nx 1 1 %s 1%% /\n' "$DF_FREE"
else
  exec /usr/bin/df "$@"
fi
EOF
if ! ln -s "$STUB" "$WORK/.linktest" 2>/dev/null; then
  # Windows 没有创建符号链接的权限时，用目录联接代替。只支持 ln -sfn <目标> <链接>。
  cat > "$STUB/ln" <<'EOF'
#!/bin/bash
target="${@: -2:1}"
link="${@: -1}"
if [ -e "$link" ] || [ -L "$link" ]; then
  cmd //c rmdir "$(cygpath -w "$link")" > /dev/null
fi
cmd //c mklink //J "$(cygpath -w "$link")" "$(cygpath -w "$target")" > /dev/null
EOF
fi
rm -f "$WORK/.linktest"
chmod +x "$STUB"/*
export PATH="$STUB:$PATH"

# make_pkg <component> <version> <dir> <mtime>
make_pkg() {
  local comp="$1" ver="$2" dir="$3" stamp="$4"
  local files="" f rel h
  mkdir -p "$dir"
  sed 's/\r$//' "$SRC" > "$dir/install.sh"
  echo "$ver" > "$dir/VERSION"
  if [ "$comp" = platform ]; then
    mkdir -p "$dir/backend"
    echo "$ver" > "$dir/backend/VERSION"
    if [ "$ver" = 1.0.0 ]; then
      mkdir -p "$dir/backend/images/calibration_images"
      echo dev > "$dir/backend/images/calibration_images/calibration_2.jpg"
    fi
  else
    mkdir -p "$dir/edge-agent"
    echo "$ver" > "$dir/edge-agent/VERSION"
  fi
  while IFS= read -r f; do
    rel="${f#"$dir/"}"
    h="$(sha256sum "$f" | cut -d' ' -f1)"
    files="$files{\"path\":\"$rel\",\"sha256\":\"$h\"},"
  done < <(find "$dir" -type f ! -name manifest.json | sort)
  printf '{"component":"%s","version":"%s","min_version":"1.0.0","python":"3.10","files":[%s]}' \
    "$comp" "$ver" "${files%,}" > "$dir/manifest.json"
  touch -d "$stamp" "$dir"
}

status_of() { cat "$1/incoming/$2.status.json"; }
current_of() { basename "$(readlink -f "$1/current")"; }

# ---------------- 平台 ----------------
P="$WORK/platform"
mkdir -p "$P/updater" "$P/incoming" "$P/releases" "$P/data/instance" "$P/data/data"
touch "$P/updater/docker-compose.yml"
export SJIC_ROOT="$P"
i=0
for v in 1.0.0 1.1.0 1.2.0 1.3.0 1.4.0; do
  i=$((i + 1))
  make_pkg platform "$v" "$WORK/pkg-p-$v" "2026-01-0$i 10:00"
done

bash "$WORK/pkg-p-1.0.0/install.sh" > "$WORK/out.txt" 2>&1
check "首装平台成功" '[ $? -eq 0 ] || true; [ "$(current_of "$P")" = 1.0.0 ]'
check "首装状态 success" 'grep -q "\"state\":\"success\"" "$P/incoming/platform.status.json"'
check "首装不调用 stop" '! grep -q " stop backend" "$P/docker.log"'

echo old > "$P/data/instance/app.db"
echo oldwal > "$P/data/instance/app.db-wal"
echo shm > "$P/data/instance/app.db-shm"
echo site > "$P/releases/1.0.0/backend/images/calibration_images/calibration_5.jpg"
: > "$P/docker.log"

FAIL_MIGRATION=1 bash "$WORK/pkg-p-1.1.0/install.sh" > "$WORK/out.txt" 2>&1
code=$?
check "迁移失败返回非 0" '[ $code -ne 0 ]'
check "迁移失败后切回 1.0.0" '[ "$(current_of "$P")" = 1.0.0 ]'
check "迁移失败后数据库恢复" '[ "$(cat "$P/data/instance/app.db")" = old ]'
check "迁移失败后 wal 恢复" '[ "$(cat "$P/data/instance/app.db-wal")" = oldwal ]'
check "迁移失败后 shm 删除" '[ ! -e "$P/data/instance/app.db-shm" ]'
check "迁移失败状态" 'grep -q "数据库迁移失败" "$P/incoming/platform.status.json"'
check "先停服再迁移再启动" 'grep -n "" "$P/docker.log" | grep -E " stop backend| run --rm" | head -2 | grep -q " stop backend"'

: > "$P/docker.log"
bash "$WORK/pkg-p-1.1.0/install.sh" > "$WORK/out.txt" 2>&1
check "升级 1.1.0 成功" '[ "$(current_of "$P")" = 1.1.0 ]'
check "顺序 stop -> run -> up" '[ "$(grep -oE "stop backend|run --rm|up -d" "$P/docker.log" | tr "\n" ,)" = "stop backend,run --rm,up -d," ]'
check "现场标定图被拷到数据目录" '[ -f "$P/data/data/images/calibration_images/calibration_5.jpg" ]'
check "包里自带的标定图不拷" '[ ! -e "$P/data/data/images/calibration_images/calibration_2.jpg" ]'
check "备份含 wal" 'ls "$P"/data/instance/backups/*/app.db-wal > /dev/null 2>&1'

echo newer > "$P/data/data/images/calibration_images/calibration_5.jpg"
for v in 1.2.0 1.3.0 1.4.0; do
  bash "$WORK/pkg-p-$v/install.sh" > "$WORK/out.txt" 2>&1 || cat "$WORK/out.txt"
done
check "升到 1.4.0" '[ "$(current_of "$P")" = 1.4.0 ]'
check "保留 3 个版本目录" '[ "$(ls -1d "$P"/releases/*/ | wc -l)" -eq 3 ]'
check "保留 1.3.0 和 1.2.0" '[ -d "$P/releases/1.3.0" ] && [ -d "$P/releases/1.2.0" ] && [ ! -d "$P/releases/1.0.0" ]'
check "备份最多 3 份" '[ "$(ls -1d "$P"/data/instance/backups/*/ | wc -l)" -eq 3 ]'
check "已有图片不被旧目录覆盖" '[ "$(cat "$P/data/data/images/calibration_images/calibration_5.jpg")" = newer ]'

DF_FREE=100 bash "$WORK/pkg-p-1.4.0/install.sh" > "$WORK/out.txt" 2>&1
code=$?
check "磁盘不足拒绝" '[ $code -ne 0 ] && grep -q "磁盘剩余 100 MB" "$P/incoming/platform.status.json"'
check "磁盘不足不动版本" '[ "$(current_of "$P")" = 1.4.0 ]'

# ---------------- 边缘 ----------------
E="$WORK/edge"
mkdir -p "$E/updater" "$E/incoming" "$E/releases"
touch "$E/updater/docker-compose.yml"
export SJIC_ROOT="$E"
i=0
for v in 1.0.0 1.1.0 1.2.0; do
  i=$((i + 1))
  make_pkg edge "$v" "$WORK/pkg-e-$v" "2026-02-0$i 10:00"
done

SJIC_EDGE_INLINE=1 bash "$WORK/pkg-e-1.0.0/install.sh" > "$WORK/out.txt" 2>&1
check "首装边缘同步执行成功" '[ "$(current_of "$E")" = 1.0.0 ] && [ ! -f "$E/systemd.log" ]'

bash "$WORK/pkg-e-1.1.0/install.sh" > "$WORK/out.txt" 2>&1
check "升级经 systemd-run 执行" 'grep -q "unit=sjic-edge-upgrade" "$E/systemd.log"'
check "升级 1.1.0 成功" '[ "$(current_of "$E")" = 1.1.0 ] && grep -q "\"state\":\"success\"" "$E/incoming/edge.status.json"'
check "临时任务目录已清理" '[ ! -d "$E/incoming/edge-job" ]'

EDGE_READY=0 bash "$WORK/pkg-e-1.2.0/install.sh" > "$WORK/out.txt" 2>&1
check "没有 ready 就回滚" '[ "$(current_of "$E")" = 1.1.0 ]'
check "回滚状态" 'grep -q "3 分钟内没有正常运行" "$E/incoming/edge.status.json"'

SYSTEMCTL_ACTIVE=1 bash "$WORK/pkg-e-1.2.0/install.sh" > "$WORK/out.txt" 2>&1
code=$?
check "已有升级时拒绝" '[ $code -ne 0 ] && grep -q "已有升级正在执行" "$E/incoming/edge.status.json"'

DF_FREE=100 bash "$WORK/pkg-e-1.2.0/install.sh" > "$WORK/out.txt" 2>&1
code=$?
check "边缘磁盘不足拒绝" '[ $code -ne 0 ] && grep -q "磁盘剩余 100 MB" "$E/incoming/edge.status.json" && [ "$(current_of "$E")" = 1.1.0 ]'

echo "passed=$PASS failed=$FAIL"
rm -rf "$WORK"
[ "$FAIL" -eq 0 ]
