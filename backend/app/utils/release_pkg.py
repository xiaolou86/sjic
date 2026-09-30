"""供管理平台调用的发版包校验入口。实现放在宿主机脚本里，避免两份签名逻辑。"""
import importlib.util
from pathlib import Path


def read_version(default='1.0.0'):
    path = Path(__file__).resolve().parents[2] / 'VERSION'
    try:
        text = path.read_text(encoding='utf-8').strip()
    except OSError:
        return default
    return text or default


def load_verifier():
    candidates = [
        Path(__file__).resolve().parents[3] / 'deploy' / 'verify_release.py',
        Path('/opt/sjic/updater/verify_release.py'),
    ]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location('sjic_verify_release', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError('找不到 verify_release.py，请先执行 install-host.sh')
