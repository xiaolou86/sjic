"""下载管理平台下发的边缘安装包，并交给宿主机脚本替换应用目录。"""
import hashlib
import json
import logging
import os
import subprocess
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

INCOMING = os.environ.get('SJIC_INCOMING', '/opt/sjic/incoming')
APPLY_SCRIPT = os.environ.get('SJIC_EDGE_APPLY', '/opt/sjic/updater/apply-edge.sh')
HOST_STATUS = os.path.join(INCOMING, 'edge.status.json')
READY_FILE = os.path.join(INCOMING, 'edge.ready')
# 宿主机脚本只做校验、解压，然后交给 systemd，正常几十秒内返回。
HOST_SCRIPT_TIMEOUT = 600
# 交给 systemd 后，本容器会在几秒内被重建；超过这个时间还活着说明宿主机没有接手。
HANDOFF_TIMEOUT = 300


def read_version():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'VERSION')
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip() or '1.0.0'
    except OSError:
        return '1.0.0'


def read_host_status():
    try:
        with open(HOST_STATUS, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_ready():
    """宿主机升级脚本等这个文件出现且版本一致，才认为新版本启动成功。"""
    if not os.path.isdir(INCOMING):
        return
    try:
        with open(READY_FILE, 'w', encoding='utf-8') as handle:
            handle.write(read_version() + '\n')
    except OSError as exc:
        logger.warning(f'Failed to write {READY_FILE}: {exc}')


def _version_tuple(text):
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


def _version_gte(left, right):
    current = list(_version_tuple(left))
    required = list(_version_tuple(right))
    width = max(len(current), len(required))
    current.extend([0] * (width - len(current)))
    required.extend([0] * (width - len(required)))
    return tuple(current) >= tuple(required)


def resolve_download_url(config, url):
    raw = (url or '').strip()
    api = ((config.get('platform') or {}).get('api_base_url') or '').strip()
    parsed = urlparse(api)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError('无法从 platform.api_base_url 推导升级包下载地址')
    if raw.startswith('http://') or raw.startswith('https://'):
        # MQTT 允许匿名发布，不能让任意地址的包进入宿主机升级脚本。
        if urlparse(raw).hostname != parsed.hostname:
            raise ValueError('只接受管理平台地址的升级包')
        return raw
    path = raw if raw.startswith('/') else '/' + raw
    return f'{parsed.scheme}://{parsed.hostname}:38880{path}'


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _report(mqtt_client, status, message):
    mqtt_client.publish_upgrade_status(status, message, read_version())


def _remove_old_packages():
    for name in os.listdir(INCOMING):
        if name.startswith('sjic-edge-') and name.endswith('.tar.gz'):
            try:
                os.remove(os.path.join(INCOMING, name))
            except OSError:
                pass


def _clear_host_status():
    try:
        os.remove(HOST_STATUS)
    except OSError:
        pass


def _host_failure_message():
    status = read_host_status() or {}
    if status.get('state') == 'failed' and status.get('message'):
        return status['message']
    return '宿主机升级脚本执行失败'


def _wait_for_replacement(mqtt_client):
    """宿主机接手后会重建本容器，本进程随之结束；在那之前宿主机报告失败，就上报并恢复接收任务。"""
    deadline = time.time() + HANDOFF_TIMEOUT
    while time.time() < deadline:
        state = (read_host_status() or {}).get('state')
        if state == 'failed':
            _report(mqtt_client, 'failed', _host_failure_message())
            return
        if state == 'success':
            return
        time.sleep(3)
    _report(mqtt_client, 'failed', '宿主机没有在预期时间内完成升级')


def run_upgrade(mqtt_client, config, task_manager, data):
    version = str((data or {}).get('version') or '').strip()
    expected = str((data or {}).get('sha256') or '').strip().lower()
    min_version = str((data or {}).get('min_version') or '1.0.0').strip()
    try:
        download_url = resolve_download_url(config, (data or {}).get('url'))
    except ValueError as exc:
        _report(mqtt_client, 'failed', str(exc))
        return
    if not version or not expected or not download_url:
        _report(mqtt_client, 'failed', '升级指令缺少版本或下载地址')
        return
    if not _version_gte(read_version(), min_version):
        _report(mqtt_client, 'failed', f'当前版本低于要求的 {min_version}')
        return
    running = list(task_manager.active_tasks.keys())
    if running:
        _report(mqtt_client, 'failed', f'节点上还有 {len(running)} 个任务在运行，请先停止后再升级')
        return

    os.makedirs(INCOMING, exist_ok=True)
    _remove_old_packages()
    package_path = os.path.join(INCOMING, f'sjic-edge-{version}.tar.gz')
    _report(mqtt_client, 'downloading', f'正在下载 {version}')
    try:
        with requests.get(download_url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with open(package_path, 'wb') as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        actual = _sha256(package_path)
        if actual != expected:
            _report(mqtt_client, 'failed', '安装包校验和不匹配')
            return
    except Exception as exc:
        logger.error(f'Edge upgrade download failed: {exc}')
        _report(mqtt_client, 'failed', '下载安装包失败')
        return

    _report(mqtt_client, 'installing', f'正在安装 {version}')
    _clear_host_status()
    command = ['nsenter', '-t', '1', '-m', '-u', '-i', '-n', '-p', '--', 'bash', APPLY_SCRIPT, package_path, expected]
    try:
        result = subprocess.run(command, start_new_session=True, timeout=HOST_SCRIPT_TIMEOUT)
    except subprocess.TimeoutExpired:
        _report(mqtt_client, 'failed', '宿主机升级脚本超时')
        return
    except Exception as exc:
        logger.error(f'Failed to start host upgrade script: {exc}')
        _report(mqtt_client, 'failed', '无法调用宿主机升级脚本，请先执行 install-host.sh')
        return
    if result.returncode != 0:
        _report(mqtt_client, 'failed', _host_failure_message())
        return
    _wait_for_replacement(mqtt_client)
