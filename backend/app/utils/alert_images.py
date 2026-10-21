"""告警图片的存放、删除和按时间清理。

新图片按小时分子目录，避免告警根目录里堆几十万个文件后 ls 卡住：

    alerts/2026/10/21/18/edge_alert_20261021_181430_123456.jpg
    alerts/2026/10/21/18/edge_alert_20261021_181430_123456_raw.jpg

alerts.image_url 只存相对路径。以前平铺在根目录的文件名仍然能打开、能删。

在服务器上先统计（不改数据）。容器里：

    python /app/app/utils/alert_images.py --db /app/instance/app.db --dir /app/alerts --days 30 --relocate --orphans

确认条数后追加 --apply。宿主机路径是
/opt/sjic/data/instance/app.db 和 /opt/sjic/data/alerts。
中断后可以再执行，已经删掉或挪走的会跳过。
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
_MANAGED_NAME = re.compile(r'^[A-Za-z0-9_-]+_\d{8}_\d{6}_\d+(_raw)?$')
_BATCH = 400


def _log(message):
    print(message, flush=True)


def _safe_prefix(prefix):
    text = re.sub(r'[^A-Za-z0-9_-]+', '_', str(prefix or '')).strip('_')
    return text[:40]


def safe_relative(value):
    """变成告警目录下的相对路径。绝对路径、.. 和空值都拒绝。"""
    if not isinstance(value, str):
        return None
    text = value.strip().replace('\\', '/')
    if not text or '\x00' in text:
        return None
    if text.startswith('http://') or text.startswith('https://'):
        marker = '/api/alerts/images/'
        idx = text.find(marker)
        text = text[idx + len(marker):] if idx >= 0 else text.rsplit('/', 1)[-1]
    marker = '/api/alerts/images/'
    if text.startswith(marker):
        text = text[len(marker):]
    text = text.lstrip('/')
    if not text or ':' in text:
        return None
    parts = []
    for part in text.split('/'):
        if part in ('', '.'):
            continue
        if part == '..' or part.startswith('..'):
            return None
        parts.append(part)
    if not parts:
        return None
    return '/'.join(parts)


def _inside(root, path):
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def alert_file_path(folder, relative):
    """相对路径对应的绝对路径。跳出告警目录时返回 None。"""
    rel = safe_relative(relative)
    if not rel or not folder:
        return None
    root = os.path.realpath(folder)
    full = os.path.realpath(os.path.join(root, *rel.split('/')))
    if full == root or not _inside(root, full):
        return None
    return full


def companion_raw_rel(relative):
    """带框图相对路径对应的原图。已经是原图则返回 None。"""
    rel = safe_relative(relative)
    if not rel:
        return None
    directory, _, base = rel.rpartition('/')
    stem, ext = os.path.splitext(base)
    if not stem or stem.endswith('_raw'):
        return None
    raw_name = f"{stem}_raw{ext or '.jpg'}"
    return f'{directory}/{raw_name}' if directory else raw_name


def annotated_of(relative):
    rel = safe_relative(relative)
    if not rel:
        return None
    directory, _, base = rel.rpartition('/')
    stem, ext = os.path.splitext(base)
    if not stem.endswith('_raw'):
        return rel
    stem = stem[:-4]
    if not stem:
        return None
    base = stem + (ext or '.jpg')
    return f'{directory}/{base}' if directory else base


def is_referenced(relative, referenced):
    rel = safe_relative(relative)
    if not rel:
        return False
    if rel in referenced:
        return True
    annotated = annotated_of(rel)
    if annotated and annotated in referenced:
        return True
    raw = companion_raw_rel(annotated) if annotated else None
    return bool(raw and raw in referenced and rel == annotated)


def is_managed_alert_name(name):
    stem, ext = os.path.splitext(os.path.basename(name or ''))
    if ext.lower() not in IMAGE_EXTS:
        return False
    return bool(_MANAGED_NAME.match(stem))


def allocate_alert_relpath(when=None, prefix='edge_alert'):
    when = when or datetime.now()
    token = _safe_prefix(prefix) or 'edge_alert'
    name = f"{token}_{when.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    return f"{when:%Y}/{when:%m}/{when:%d}/{when:%H}/{name}"


def save_alert_upload(folder, image_file, raw_file=None, when=None, prefix='edge_alert'):
    """保存带框图和可选原图，返回写入数据库的相对路径。"""
    if not folder:
        raise ValueError('alert folder is empty')
    os.makedirs(folder, exist_ok=True)
    rel = allocate_alert_relpath(when=when, prefix=prefix)
    dest = alert_file_path(folder, rel)
    if dest is None:
        raise ValueError('unsafe alert path')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    image_file.save(dest)
    if raw_file:
        raw_rel = companion_raw_rel(rel)
        raw_dest = alert_file_path(folder, raw_rel)
        if raw_dest is None:
            raise ValueError('unsafe raw alert path')
        os.makedirs(os.path.dirname(raw_dest), exist_ok=True)
        raw_file.save(raw_dest)
    return rel


def stored_image_paths(folder, image_url):
    rel = safe_relative(image_url)
    if not rel:
        return []
    paths = []
    for item in (rel, companion_raw_rel(rel)):
        if not item:
            continue
        path = alert_file_path(folder, item)
        if path and path not in paths:
            paths.append(path)
    return paths


def prune_up(folder, start):
    """删掉已经空了的小时/日/月/年目录，停在告警根目录。"""
    root = os.path.realpath(folder)
    current = os.path.realpath(start)
    while current != root and _inside(root, current):
        try:
            os.rmdir(current)
        except OSError:
            return
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


def delete_stored_images(folder, image_url, log=None):
    """删除一条告警的带框图和原图。返回实际删掉的文件数。"""
    removed = 0
    parents = []
    report = log or _log
    for path in stored_image_paths(folder, image_url):
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
        except OSError as exc:
            report(f'删除失败 {path}: {exc}')
            continue
        removed += 1
        parents.append(os.path.dirname(path))
    for parent in parents:
        prune_up(folder, parent)
    return removed


def count_existing_images(folder, image_url):
    return sum(1 for path in stored_image_paths(folder, image_url) if os.path.isfile(path))


def assert_alert_dir(folder):
    if not folder or not os.path.isdir(folder):
        raise ValueError(f'目录不存在: {folder}')
    real = os.path.realpath(folder)
    parent = os.path.dirname(real)
    if parent == real:
        raise ValueError(f'不能对磁盘根目录操作: {real}')
    return real


def parse_before(text):
    raw = str(text).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError('时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS')


def _cutoff_text(before):
    moment = before if isinstance(before, datetime) else parse_before(before)
    return moment.strftime('%Y-%m-%d %H:%M:%S')


def _hour_bucket(timestamp_text, filename):
    text = (timestamp_text or '').strip()
    if len(text) >= 13 and text[4] == '-' and text[7] == '-' and text[10] == ' ':
        year, month, day, hour = text[0:4], text[5:7], text[8:10], text[11:13]
        if year.isdigit() and month.isdigit() and day.isdigit() and hour.isdigit():
            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31 and 0 <= int(hour) <= 23:
                return f'{year}/{month}/{day}/{hour}'
    match = re.search(r'(\d{4})(\d{2})(\d{2})_(\d{2})\d{4}_', filename or '')
    if not match:
        return None
    year, month, day, hour = match.groups()
    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31 and 0 <= int(hour) <= 23:
        return f'{year}/{month}/{day}/{hour}'
    return None


def _connect(db_path, apply):
    if not os.path.isfile(db_path):
        raise ValueError(f'数据库不存在: {db_path}')
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.execute('PRAGMA busy_timeout=30000')
    if not apply:
        try:
            conn.execute('PRAGMA query_only=ON')
        except sqlite3.Error:
            pass
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alerts'"
    ).fetchone()
    if not found:
        conn.close()
        raise ValueError('数据库里没有 alerts 表')
    return conn


def _commit_write(conn, sql, params, many=False):
    conn.execute('BEGIN IMMEDIATE')
    try:
        if many:
            conn.executemany(sql, params)
        else:
            conn.execute(sql, params)
        conn.execute('COMMIT')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise


def _planned(total, limit):
    if limit and limit < total:
        return limit
    return total


def purge_old_alerts(conn, folder, cutoff, apply, limit, log):
    log(f'正在统计早于 {cutoff} 的告警')
    total = conn.execute(
        'SELECT COUNT(*) FROM alerts WHERE timestamp IS NOT NULL AND timestamp < ?',
        (cutoff,),
    ).fetchone()[0]
    planned = _planned(total, limit)
    if not total:
        log(f'没有早于 {cutoff} 的告警')
        return {'purge_alerts': 0, 'purge_files': 0}
    verb = '将删除' if not apply else '开始删除'
    log(f'{verb}早于 {cutoff} 的告警 {planned} 条（共 {total} 条）')
    last_id = 0
    seen = 0
    files = 0
    while True:
        if limit and seen >= limit:
            break
        batch = _BATCH if not limit else min(_BATCH, limit - seen)
        rows = conn.execute(
            '''SELECT id, image_url FROM alerts
               WHERE timestamp IS NOT NULL AND timestamp < ? AND id > ?
               ORDER BY id LIMIT ?''',
            (cutoff, last_id, batch),
        ).fetchall()
        if not rows:
            break
        if apply:
            ids = []
            for row_id, image_url in rows:
                files += delete_stored_images(folder, image_url, log=log)
                ids.append(row_id)
            _commit_write(
                conn,
                f"DELETE FROM alerts WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
        else:
            for _row_id, image_url in rows:
                files += count_existing_images(folder, image_url)
        last_id = rows[-1][0]
        seen += len(rows)
        log(f'已处理告警 {seen}/{planned}')
    done = '已删除' if apply else '将删除'
    log(f'{done}告警记录 {seen} 条，图片 {files} 个')
    return {'purge_alerts': seen, 'purge_files': files}


def _move_pair(folder, src_rel, dest_rel, apply):
    """移动带框图和原图。目标已存在返回 None。返回移动的文件数。"""
    pairs = [(src_rel, dest_rel)]
    raw_src = companion_raw_rel(src_rel)
    raw_dest = companion_raw_rel(dest_rel)
    if raw_src and raw_dest:
        pairs.append((raw_src, raw_dest))
    pending = []
    for src_item, dest_item in pairs:
        src = alert_file_path(folder, src_item)
        dest = alert_file_path(folder, dest_item)
        if src is None or dest is None:
            return None
        src_exists = os.path.isfile(src)
        dest_exists = os.path.isfile(dest)
        if src_exists and dest_exists:
            return None
        if src_exists:
            pending.append((src, dest))
    if not apply:
        return len(pending)
    moved = []
    try:
        for src, dest in pending:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(src, dest)
            moved.append((dest, src))
        return len(pending)
    except OSError:
        for dest, src in reversed(moved):
            try:
                os.replace(dest, src)
            except OSError:
                pass
        raise


def relocate_flat_alerts(conn, folder, cutoff, apply, limit, log):
    where = (
        "image_url IS NOT NULL AND image_url != '' "
        "AND instr(image_url, '/') = 0 AND instr(image_url, char(92)) = 0"
    )
    params = []
    if cutoff:
        where += ' AND (timestamp IS NULL OR timestamp >= ?)'
        params.append(cutoff)
    log('正在统计仍平铺在根目录的告警图片')
    total = conn.execute(f'SELECT COUNT(*) FROM alerts WHERE {where}', params).fetchone()[0]
    planned = _planned(total, limit)
    if not total:
        log('没有仍平铺在根目录的告警图片')
        return {'relocate_alerts': 0, 'relocate_files': 0, 'relocate_skipped': 0}
    verb = '将挪入小时目录' if not apply else '开始挪入小时目录'
    log(f'{verb} {planned} 条（共 {total} 条）')
    last_id = 0
    seen = 0
    moved_rows = 0
    moved_files = 0
    skipped = 0
    while True:
        if limit and seen >= limit:
            break
        batch = _BATCH if not limit else min(_BATCH, limit - seen)
        rows = conn.execute(
            f'''SELECT id, timestamp, image_url FROM alerts
                WHERE id > ? AND {where}
                ORDER BY id LIMIT ?''',
            [last_id, *params, batch],
        ).fetchall()
        if not rows:
            break
        updates = []
        for row_id, timestamp_text, image_url in rows:
            rel = safe_relative(image_url)
            bucket = _hour_bucket(timestamp_text, rel or '')
            if not rel or not bucket:
                skipped += 1
                continue
            dest_rel = f'{bucket}/{os.path.basename(rel)}'
            try:
                count = _move_pair(folder, rel, dest_rel, apply)
            except OSError as exc:
                log(f'移动失败 id={row_id}: {exc}')
                skipped += 1
                continue
            if count is None:
                skipped += 1
                continue
            moved_files += count
            moved_rows += 1
            if apply:
                updates.append((dest_rel, row_id))
        if apply and updates:
            _commit_write(conn, 'UPDATE alerts SET image_url=? WHERE id=?', updates, many=True)
        last_id = rows[-1][0]
        seen += len(rows)
        log(f'已处理平铺图片 {seen}/{planned}')
    done = '已调整' if apply else '将调整'
    log(f'{done}告警记录 {moved_rows} 条，移动图片 {moved_files} 个，跳过 {skipped} 条')
    return {
        'relocate_alerts': moved_rows,
        'relocate_files': moved_files,
        'relocate_skipped': skipped,
    }


def _load_referenced(conn):
    refs = set()
    for (image_url,) in conn.execute('SELECT image_url FROM alerts'):
        rel = safe_relative(image_url or '')
        if rel:
            refs.add(rel)
    return refs


def _walk_files(folder, log):
    stack = [folder]
    scanned = 0
    while stack:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except OSError as exc:
            log(f'无法读取目录 {current}: {exc}')
            continue
        with iterator:
            for entry in iterator:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                scanned += 1
                if scanned % 20000 == 0:
                    log(f'已扫描 {scanned} 个文件')
                yield entry
    log(f'扫描结束，共 {scanned} 个文件')


def delete_orphan_files(conn, folder, apply, grace_seconds, log):
    referenced = _load_referenced(conn)
    verb = '将删除' if not apply else '开始删除'
    log(f'{verb}没有任何告警记录指向的图片（{grace_seconds // 60} 分钟内的新文件会留下）')
    now = time.time()
    removed = 0
    parents = []
    root = os.path.realpath(folder)
    for entry in _walk_files(root, log):
        if not is_managed_alert_name(entry.name):
            continue
        rel = os.path.relpath(entry.path, root).replace('\\', '/')
        if is_referenced(rel, referenced):
            continue
        try:
            if grace_seconds and now - entry.stat(follow_symlinks=False).st_mtime < grace_seconds:
                continue
        except OSError:
            continue
        if not apply:
            removed += 1
            continue
        try:
            os.remove(entry.path)
        except OSError as exc:
            log(f'删除失败 {entry.path}: {exc}')
            continue
        removed += 1
        parents.append(os.path.dirname(entry.path))
    for parent in parents:
        prune_up(folder, parent)
    done = '已删除' if apply else '将删除'
    log(f'{done}无记录图片 {removed} 个')
    return {'orphan_files': removed}


def run_cleanup(db_path, folder, before=None, apply=False, limit=0, relocate=False,
                remove_orphans=False, orphan_grace_seconds=900, log=None):
    """按时间删除告警和图片，并可把根目录里剩下的图片挪进小时目录。"""
    report = log or _log
    folder = assert_alert_dir(folder)
    report(f'数据库: {os.path.abspath(db_path)}')
    report(f'图片目录: {folder}')
    report('模式: 删除并移动' if apply else '模式: 只统计，不会改动文件或数据库')
    conn = _connect(db_path, apply)
    try:
        result = {'apply': bool(apply)}
        cutoff = _cutoff_text(before) if before is not None else None
        if cutoff:
            result.update(purge_old_alerts(conn, folder, cutoff, apply, limit, report))
        if relocate:
            result.update(relocate_flat_alerts(conn, folder, cutoff, apply, limit, report))
        if remove_orphans:
            result.update(delete_orphan_files(conn, folder, apply, orphan_grace_seconds, report))
        if not apply:
            report('这是统计，没有删除或移动文件。确认后追加 --apply')
        else:
            report('完成。图片占用的磁盘会马上释放。数据库文件要等 VACUUM 才会变小，可以先不做。')
        return result
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='按时间删除告警记录和图片。默认只统计，加上 --apply 才真正改动。',
    )
    parser.add_argument('--db', required=True, help='SQLite 数据库文件，例如 /app/instance/app.db')
    parser.add_argument('--dir', required=True, help='告警图片目录，例如 /app/alerts')
    parser.add_argument('--before', help='删除该时间之前的告警，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--days', type=int, help='删除早于 N 天前的告警，N 至少为 1')
    parser.add_argument('--relocate', action='store_true', help='把仍平铺在根目录、并且保留的图片挪进 年/月/日/小时 目录')
    parser.add_argument('--orphans', action='store_true', help='删除没有任何告警记录指向的告警图片')
    parser.add_argument('--orphan-grace-minutes', type=int, default=15, help='保留最近这么多分钟内的无记录图片，默认 15')
    parser.add_argument('--limit', type=int, default=0, help='最多处理多少条告警，0 表示不限制')
    parser.add_argument('--apply', action='store_true', help='真正删除和移动。不加这个参数只会统计')
    args = parser.parse_args(argv)

    if args.days is not None and args.before:
        print('请只指定 --before 或 --days 其中一个', file=sys.stderr)
        return 2
    if args.days is None and not args.before and not args.relocate and not args.orphans:
        print('请指定 --before、--days、--relocate 或 --orphans', file=sys.stderr)
        return 2
    if args.days is not None and args.days < 1:
        print('--days 至少为 1', file=sys.stderr)
        return 2
    if args.limit < 0 or args.orphan_grace_minutes < 0:
        print('--limit 和 --orphan-grace-minutes 不能是负数', file=sys.stderr)
        return 2

    before = None
    if args.before:
        before = parse_before(args.before)
    elif args.days is not None:
        before = datetime.now() - timedelta(days=args.days)

    try:
        run_cleanup(
            args.db,
            args.dir,
            before=before,
            apply=args.apply,
            limit=args.limit,
            relocate=args.relocate,
            remove_orphans=args.orphans,
            orphan_grace_seconds=args.orphan_grace_minutes * 60,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
