"""校验发版安装包。

安装包内不包含本文件。宿主机升级器把这份脚本放在 /opt/sjic/updater，
发版 tarball 只带 .pyc、前端静态文件和 install.sh。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import tarfile
from pathlib import Path


class ReleaseError(Exception):
    pass


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_version(text: str) -> tuple:
    parts = []
    for piece in str(text or '0').split('.'):
        number = ''
        for char in piece:
            if char.isdigit():
                number += char
            else:
                break
        parts.append(int(number or '0'))
    return tuple(parts)


def version_gte(left: str, right: str) -> bool:
    current = list(parse_version(left))
    required = list(parse_version(right))
    width = max(len(current), len(required))
    current.extend([0] * (width - len(current)))
    required.extend([0] * (width - len(required)))
    return tuple(current) >= tuple(required)


def build_manifest(manifest: dict) -> dict:
    body = dict(manifest)
    body.pop('signature', None)
    body['min_version'] = body.get('min_version') or '1.0.0'
    body['python'] = body.get('python') or '3.10'
    return body


def _safe_members(archive: tarfile.TarFile):
    for member in archive.getmembers():
        name = member.name.replace('\\', '/')
        if name.startswith('/') or name.startswith('../') or '/../' in f'/{name}/':
            raise ReleaseError(f'安装包包含非法路径: {member.name}')
        if member.issym() or member.islnk():
            raise ReleaseError(f'安装包不允许链接: {member.name}')
        yield member


def _extract(archive_path: str, dest: str) -> None:
    with tarfile.open(archive_path, 'r:gz') as archive:
        archive.extractall(dest, members=_safe_members(archive))


def verify_tree(root: str, manifest: dict, current_version: str = '') -> dict:
    component = manifest.get('component')
    if component not in ('platform', 'edge'):
        raise ReleaseError('manifest.component 须为 platform 或 edge')
    version = str(manifest.get('version') or '').strip()
    if not version:
        raise ReleaseError('manifest 缺少 version')
    python_version = str(manifest.get('python') or '3.10')
    if not python_version.startswith('3.10'):
        raise ReleaseError(f'安装包字节码版本为 {python_version}，现场需要 Python 3.10')

    files = manifest.get('files') or []
    if not isinstance(files, list) or not files:
        raise ReleaseError('manifest 缺少文件清单')

    min_version = manifest.get('min_version') or '1.0.0'
    if current_version and not version_gte(current_version, min_version):
        raise ReleaseError(f'当前版本 {current_version} 低于安装包要求的最低版本 {min_version}')

    listed = {}
    for item in files:
        rel = str(item.get('path') or '').replace('\\', '/')
        if not rel or rel.startswith('/') or '..' in rel.split('/'):
            raise ReleaseError(f'文件清单路径非法: {rel}')
        if rel == 'manifest.json' or rel.endswith('.py'):
            raise ReleaseError(f'文件清单不允许包含: {rel}')
        listed[rel] = str(item.get('sha256') or '')

    root_path = Path(root)
    seen = set()
    for path in root_path.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root_path).as_posix()
        if rel == 'manifest.json':
            continue
        if rel.endswith('.py'):
            raise ReleaseError(f'安装包含有 Python 源码: {rel}')
        if rel not in listed:
            raise ReleaseError(f'安装包含有未登记文件: {rel}')
        actual = sha256_file(str(path))
        if not hmac.compare_digest(actual, listed[rel]):
            raise ReleaseError(f'文件校验失败: {rel}')
        seen.add(rel)

    missing = sorted(set(listed) - seen)
    if missing:
        raise ReleaseError(f'安装包缺少文件: {missing[0]}')
    return manifest


def verify_tarball(archive_path: str, expected_sha256: str = '', current_version: str = '') -> dict:
    if expected_sha256:
        actual = sha256_file(archive_path)
        if not hmac.compare_digest(actual, expected_sha256.strip().lower()):
            raise ReleaseError('安装包校验和不匹配')

    import tempfile
    with tempfile.TemporaryDirectory(prefix='sjic-release-') as temp_dir:
        _extract(archive_path, temp_dir)
        manifest_path = Path(temp_dir) / 'manifest.json'
        if not manifest_path.is_file():
            raise ReleaseError('安装包缺少 manifest.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        return verify_tree(temp_dir, manifest, current_version=current_version)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='校验 SJIC 发版安装包')
    parser.add_argument('package')
    parser.add_argument('--sha256', default='')
    parser.add_argument('--current', default='')
    args = parser.parse_args(argv)
    try:
        manifest = verify_tarball(
            args.package,
            expected_sha256=args.sha256,
            current_version=args.current,
        )
    except (ReleaseError, OSError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{manifest['component']} {manifest['version']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
