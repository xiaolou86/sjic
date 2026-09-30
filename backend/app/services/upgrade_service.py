"""保存已验签的安装包，并通知宿主机升级器。"""
import json
import os
from datetime import datetime

from flask import current_app

from app.utils.release_pkg import load_verifier, read_version


class UpgradeError(Exception):
    pass


def _path(env_name, default):
    return os.environ.get(env_name) or default


def upgrades_dir():
    path = _path('SJIC_UPGRADES', '/opt/sjic/data/upgrades')
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise UpgradeError('升级包目录不可写。请先在服务器执行 deploy/platform/install-host.sh') from exc
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass
    return path


def incoming_dir():
    path = _path('SJIC_INCOMING', '/opt/sjic/incoming')
    if not os.path.isdir(path) or not os.access(path, os.W_OK):
        raise UpgradeError('宿主机升级目录不可写。请先执行 deploy/platform/install-host.sh，并用 deploy/platform/docker-compose.yml 启动')
    return path


def _write_json(path, payload):
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(temporary, path)


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def stage_package(component, stream):
    if component not in ('platform', 'edge'):
        raise UpgradeError('未知安装包类型')
    verifier = None
    try:
        verifier = load_verifier()
    except FileNotFoundError as exc:
        raise UpgradeError(str(exc)) from exc
    directory = upgrades_dir()
    temporary = os.path.join(directory, f'.upload-{component}.tar.gz')
    stream.save(temporary)
    try:
        os.chmod(temporary, 0o644)
        manifest = verifier.verify_tarball(temporary)
        if manifest.get('component') != component:
            raise UpgradeError(f'这是{manifest.get("component")}安装包，不能当作{component}安装包')
        filename = f'sjic-{component}-{manifest["version"]}.tar.gz'
        final_path = os.path.join(directory, filename)
        os.replace(temporary, final_path)
        os.chmod(final_path, 0o644)
        meta = {
            'version': manifest['version'],
            'min_version': manifest.get('min_version') or '1.0.0',
            'filename': filename,
            'sha256': verifier.sha256_file(final_path),
            'path': final_path,
            'stored_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        _write_json(os.path.join(directory, f'{component}.json'), meta)
        return meta
    except verifier.ReleaseError as exc:
        raise UpgradeError(str(exc)) from exc
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def package_meta(component):
    directory = _path('SJIC_UPGRADES', '/opt/sjic/data/upgrades')
    meta = _read_json(os.path.join(directory, f'{component}.json'))
    if not meta:
        return None
    path = meta.get('path') or ''
    if path and not os.path.isfile(path):
        return None
    return meta


def upgrade_download_path(filename):
    import base64
    import hashlib
    import time
    secret = current_app.config['DOWNLOAD_SECURE_KEY']
    expire_time = int(time.time()) + 3600
    raw = f"{secret}/static-upgrades/{filename}{expire_time}"
    digest = hashlib.md5(raw.encode('utf-8')).digest()
    token = base64.b64encode(digest).decode('utf-8').replace('+', '-').replace('/', '_').rstrip('=')
    return f"/static-upgrades/{filename}?md5={token}&expires={expire_time}"


def request_platform_upgrade():
    meta = package_meta('platform')
    if not meta:
        raise UpgradeError('请先上传平台安装包')
    incoming = incoming_dir()
    request_path = os.path.join(incoming, 'platform.request.json')
    running_path = os.path.join(incoming, 'platform.request.running')
    if os.path.exists(request_path) or os.path.exists(running_path):
        raise UpgradeError('已有平台升级正在执行')
    _write_json(os.path.join(incoming, 'platform.status.json'), {
        'state': 'queued',
        'version': meta['version'],
        'message': '已提交给宿主机升级器',
    })
    _write_json(request_path, {'package': meta['path']})
    return meta


def platform_status():
    incoming = _path('SJIC_INCOMING', '/opt/sjic/incoming')
    status = _read_json(os.path.join(incoming, 'platform.status.json')) or {
        'state': 'idle',
        'version': '',
        'message': '',
    }
    edge = package_meta('edge')
    platform = package_meta('platform')
    return {
        'version': read_version(),
        'platform': {
            'state': status.get('state') or 'idle',
            'version': status.get('version') or '',
            'message': status.get('message') or '',
            'staged_version': (platform or {}).get('version') or '',
        },
        'edge': {
            'staged_version': (edge or {}).get('version') or '',
            'filename': (edge or {}).get('filename') or '',
        },
    }
