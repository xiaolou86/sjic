"""内置账号密码。哈希存在系统设置里，未改过则仍用出厂密码。"""
import hmac

from werkzeug.security import check_password_hash, generate_password_hash

# 出厂账号。改密后只保留哈希，不再回退出厂密码。
BUILTIN_ACCOUNTS = {
    'super_admin': {'role': 'vendor', 'password': '123123'},
    'admin': {'role': 'customer', 'password': '123123'},
}

MIN_PASSWORD_LENGTH = 6


def _stored_hash(config, username):
    accounts = (config or {}).get('accounts') or {}
    if not isinstance(accounts, dict):
        return None
    entry = accounts.get(username)
    if not isinstance(entry, dict):
        return None
    value = entry.get('password_hash')
    return value if isinstance(value, str) and value else None


def authenticate(username, password, config=None):
    """密码正确时返回角色，否则返回 None。"""
    username = username.strip() if isinstance(username, str) else ''
    password = password if isinstance(password, str) else ''
    account = BUILTIN_ACCOUNTS.get(username)
    if not account or not password:
        return None

    password_hash = _stored_hash(config, username)
    if password_hash:
        try:
            ok = check_password_hash(password_hash, password)
        except Exception:
            ok = False
    else:
        ok = hmac.compare_digest(password, account['password'])
    if not ok:
        return None
    return account['role']


def hash_password(password):
    return generate_password_hash(password)
