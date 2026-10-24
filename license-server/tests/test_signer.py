from datetime import datetime, timedelta, timezone

import pytest

import signer

KEY = 'golden-test-key'
MACHINE_CODE = 'ab' * 32

# Produced by backend/app/services/license_service.py sign_license() with KEY.
BACKEND_VECTORS = [
    (
        {
            'edition': 'official', 'customer_id': 'acme', 'machine_code': 'abc123', 'max_cameras': 16,
            'allowed_algorithms': ['b', 'a'], 'issued_at': '2026-01-01', 'expires_at': '2027-12-31',
        },
        'cfd1cb3fb6a9f24dead4573014e42faf05e55fe2dbe44481f0db1a8acaadc871',
    ),
    (
        {
            'edition': 'trial', 'customer_id': '', 'machine_code': 'abc123', 'max_cameras': 4,
            'allowed_algorithms': [], 'issued_at': '2026-01-01', 'expires_at': '2026-01-31',
        },
        '362181ce5369c41d86fcf058e974db8917fa0d6a3535cbb71ceb835a1795688b',
    ),
    (
        {
            'edition': 'official', 'customer_id': '', 'machine_code': 'abc123', 'max_cameras': 0,
            'allowed_algorithms': [], 'issued_at': '2026-01-01', 'expires_at': '2027-12-31',
        },
        '011ff757313dcb4328da9b037c88b21e1c2e35382ba43185f626b45e53cdd4df',
    ),
]


@pytest.mark.parametrize('data,expected', BACKEND_VECTORS)
def test_signature_matches_backend(data, expected):
    assert signer.sign(data, KEY) == expected


def test_trial_lasts_trial_days_and_is_signed():
    data = signer.build_license(key=KEY, edition='trial', machine_code=MACHINE_CODE.upper(), max_cameras=4)

    issued = datetime.strptime(data['issued_at'], '%Y-%m-%d')
    expires = datetime.strptime(data['expires_at'], '%Y-%m-%d')
    assert expires - issued == timedelta(days=signer.TRIAL_DAYS)
    assert data['machine_code'] == MACHINE_CODE
    assert data['signature'] == signer.sign(data, KEY)


def test_official_accepts_compact_date_and_unlimited_cameras():
    data = signer.build_license(
        key=KEY, edition='official', machine_code=MACHINE_CODE, max_cameras=0,
        expires_at='20991231', allowed_algorithms=['pose', ' ', 'belt'], customer_id=' acme ',
    )

    assert data['expires_at'] == '2099-12-31'
    assert data['max_cameras'] == 0
    assert data['allowed_algorithms'] == ['pose', 'belt']
    assert data['customer_id'] == 'acme'


@pytest.mark.parametrize('overrides', [
    {'key': ''},
    {'edition': 'pro'},
    {'machine_code': 'not-a-machine-code'},
    {'max_cameras': -1},
    {'max_cameras': 'abc'},
    {'expires_at': None},
    {'expires_at': (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()},
])
def test_rejects_licenses_the_platform_would_not_accept(overrides):
    kwargs = dict(key=KEY, edition='official', machine_code=MACHINE_CODE, max_cameras=8, expires_at='2099-12-31')
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        signer.build_license(**kwargs)
