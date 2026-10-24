"""Build and sign SJIC license files.

The canonical payload and HMAC here must stay identical to
backend/app/services/license_service.py, which verifies these signatures
on customer machines. tests/test_signer.py pins known-good vectors.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone

TRIAL_DAYS = 30
EDITIONS = ('trial', 'official')
SIGN_FIELDS = (
    'edition',
    'machine_code',
    'max_cameras',
    'expires_at',
    'allowed_algorithms',
    'issued_at',
    'customer_id',
)
MACHINE_CODE_RE = re.compile(r'^[0-9a-f]{64}$')


def format_date(value):
    """Normalize YYYY-MM-DD / YYYYMMDD / ISO datetime to YYYY-MM-DD (UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    text = str(value).strip()
    if not text:
        return None

    if len(text) >= 10 and text[4] == '-' and text[7] == '-':
        candidate = text[:10]
        try:
            datetime.strptime(candidate, '%Y-%m-%d')
            return candidate
        except ValueError:
            return None

    if len(text) == 8 and text.isdigit():
        try:
            return datetime.strptime(text, '%Y%m%d').date().isoformat()
        except ValueError:
            return None

    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def parse_date(value, *, end_of_day=False):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    date_text = format_date(value)
    if not date_text:
        return None
    year, month, day = (int(x) for x in date_text.split('-'))
    if end_of_day:
        return datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
    return datetime(year, month, day, tzinfo=timezone.utc)


def canonical_payload(data):
    payload = {}
    for field in SIGN_FIELDS:
        value = data.get(field)
        if field == 'allowed_algorithms':
            algos = value if isinstance(value, list) else []
            payload[field] = sorted(str(x) for x in algos)
        elif field == 'max_cameras':
            payload[field] = int(value or 0)
        elif field == 'edition':
            payload[field] = str(value or '').strip().lower()
        elif field in ('expires_at', 'issued_at'):
            payload[field] = format_date(value) or ''
        else:
            payload[field] = '' if value is None else str(value).strip()
    return payload


def sign(data, key):
    body = json.dumps(canonical_payload(data), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hmac.new(key.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()


def build_license(
    *,
    key,
    edition,
    machine_code,
    max_cameras,
    expires_at=None,
    allowed_algorithms=None,
    customer_id='',
    issued_at=None,
):
    """Return a signed license dict. Raises ValueError with a user-facing message."""
    if not key:
        raise ValueError('未配置签名密钥 LICENSE_SIGNING_KEY')

    edition = str(edition or '').strip().lower()
    if edition not in EDITIONS:
        raise ValueError('版本只能是 trial 或 official')

    machine_code = str(machine_code or '').strip().lower()
    if not MACHINE_CODE_RE.match(machine_code):
        raise ValueError('机器码应为 64 位十六进制字符串，请从平台「授权管理」页完整复制')

    try:
        max_cameras = int(max_cameras)
    except (TypeError, ValueError):
        raise ValueError('视频路数必须是整数') from None
    if max_cameras < 0:
        raise ValueError('视频路数不能为负数（0 表示不限）')

    now = datetime.now(timezone.utc)
    issued = parse_date(issued_at) or now
    if edition == 'trial':
        expires = issued + timedelta(days=TRIAL_DAYS)
    else:
        expires = parse_date(expires_at, end_of_day=True)
        if not expires:
            raise ValueError('正式版必须填写到期日（YYYY-MM-DD）')
    if expires < now:
        raise ValueError('到期日已过，导入时会被拒绝')

    data = {
        'edition': edition,
        'customer_id': str(customer_id or '').strip(),
        'machine_code': machine_code,
        'max_cameras': max_cameras,
        'allowed_algorithms': [str(a).strip() for a in (allowed_algorithms or []) if str(a).strip()],
        'issued_at': format_date(issued),
        'expires_at': format_date(expires),
    }
    data['signature'] = sign(data, key)
    return data
