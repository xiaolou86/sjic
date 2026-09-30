"""用 Python 3.10 把管理平台和 edge-agent 打成不含 .py 的安装包。"""
from __future__ import annotations

import argparse
import compileall
import shutil
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'deploy'))
import verify_release  # noqa: E402


SKIP_DIRS = {
    '__pycache__', '.git', '.pytest_cache', 'tests', 'instance', 'logs',
    'models', 'alerts', 'videos', 'deploy', 'node_modules', '.venv', 'venv',
}
EDGE_SKIP_FILES = {'config.yaml', '.env'}


def require_python310() -> None:
    if sys.version_info[:2] != (3, 10):
        version = '.'.join(str(part) for part in sys.version_info[:3])
        raise SystemExit(f'请使用 Python 3.10 打包，当前是 {version}。字节码必须和现场解释器一致。')


def copy_tree(source: Path, dest: Path, skip_files: set) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.rglob('*'):
        relative = path.relative_to(source)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.name in skip_files:
            continue
        target = dest / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def compile_tree(root: Path) -> None:
    compileall.compile_dir(str(root), legacy=True, force=True, quiet=1)
    for path in list(root.rglob('*')):
        if path.is_dir() and path.name == '__pycache__':
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix == '.py':
            path.unlink()


def write_version(root: Path, version: str, extra: list) -> None:
    text = version + '\n'
    (root / 'VERSION').write_text(text, encoding='utf-8')
    for path in extra:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def file_records(root: Path) -> list:
    records = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.name == 'manifest.json':
            continue
        relative = path.relative_to(root).as_posix()
        records.append({'path': relative, 'sha256': verify_release.sha256_file(str(path))})
    return records


def pack(root: Path, archive_path: Path) -> str:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, 'w:gz') as archive:
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            arcname = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=arcname)
            info.mode = 0o755 if arcname.endswith('.sh') else 0o644
            with path.open('rb') as handle:
                archive.addfile(info, handle)
    return verify_release.sha256_file(str(archive_path))


def build_component(component: str, version: str, min_version: str, output: Path) -> Path:
    staging = output.parent / f'.staging-{component}-{version}'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        install_sh = (REPO / 'deploy' / 'package_install.sh').read_bytes().replace(b'\r\n', b'\n')
        (staging / 'install.sh').write_bytes(install_sh)
        if component == 'platform':
            copy_tree(REPO / 'backend', staging / 'backend', set())
            frontend_build = REPO / 'frontend' / 'build'
            if not frontend_build.is_dir():
                raise SystemExit('缺少 frontend/build。请先在 frontend 目录执行 npm run build。')
            copy_tree(frontend_build, staging / 'frontend' / 'build', set())
            compile_tree(staging / 'backend')
            write_version(staging, version, [staging / 'backend' / 'VERSION'])
        else:
            copy_tree(REPO / 'edge-agent', staging / 'edge-agent', EDGE_SKIP_FILES)
            compile_tree(staging / 'edge-agent')
            write_version(staging, version, [staging / 'edge-agent' / 'VERSION'])

        manifest = verify_release.build_manifest({
            'component': component,
            'version': version,
            'min_version': min_version,
            'python': '3.10',
            'files': file_records(staging),
        })
        (staging / 'manifest.json').write_text(
            __import__('json').dumps(manifest, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        archive_path = output / f'sjic-{component}-{version}.tar.gz'
        digest = pack(staging, archive_path)
        verify_release.verify_tarball(str(archive_path))
        print(f'{archive_path} {digest}')
        return archive_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> None:
    require_python310()
    parser = argparse.ArgumentParser(description='打包 SJIC 安装包（仅 .pyc）')
    parser.add_argument('--version', required=True)
    parser.add_argument('--min-version', default='1.0.0')
    parser.add_argument('--component', choices=('platform', 'edge', 'all'), default='all')
    parser.add_argument('--output', default=str(REPO / 'dist'))
    args = parser.parse_args()
    output = Path(args.output)
    components = ('platform', 'edge') if args.component == 'all' else (args.component,)
    for component in components:
        build_component(component, args.version, args.min_version, output)


if __name__ == '__main__':
    main()
