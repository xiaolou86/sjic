import base64
import json

import pytest

import signer
from app import create_app

KEY = 'test-key'
MACHINE_CODE = 'cd' * 32
AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'admin:pw').decode()}


def make_app(db_path):
    return create_app({'SIGNING_KEY': KEY, 'DB_PATH': str(db_path), 'ADMIN_USER': 'admin', 'ADMIN_PASSWORD': 'pw'})


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / 'licenses.db'


@pytest.fixture
def client(db_path):
    return make_app(db_path).test_client()


def test_requires_login(client):
    assert client.get('/').status_code == 401
    bad = {'Authorization': 'Basic ' + base64.b64encode(b'admin:wrong').decode()}
    assert client.get('/', headers=bad).status_code == 401


def test_create_list_and_download(client, db_path):
    resp = client.post('/licenses', headers=AUTH, data={
        'machine_code': MACHINE_CODE, 'edition': 'official', 'expires_at': '2099-12-31',
        'max_cameras': '16', 'customer_id': '某客户', 'allowed_algorithms': 'pose，belt', 'note': '合同 A-1',
    })
    assert resp.status_code == 302
    assert 'created=1' in resp.headers['Location']

    page = client.get('/?created=1', headers=AUTH).get_data(as_text=True)
    assert MACHINE_CODE in page
    assert '某客户' in page
    assert '合同 A-1' in page

    download = client.get('/licenses/1.json', headers=AUTH)
    assert download.status_code == 200
    assert 'attachment' in download.headers['Content-Disposition']
    data = json.loads(download.get_data(as_text=True))
    assert data['allowed_algorithms'] == ['pose', 'belt']
    assert data['signature'] == signer.sign(data, KEY)
    assert 'note' not in data

    inline = client.get('/licenses/1.json?inline=1', headers=AUTH)
    assert 'attachment' not in inline.headers.get('Content-Disposition', '')

    # Records survive a restart against the same database file.
    page = make_app(db_path).test_client().get('/', headers=AUTH).get_data(as_text=True)
    assert MACHINE_CODE in page


def test_invalid_input_keeps_form_and_saves_nothing(client):
    resp = client.post('/licenses', headers=AUTH, data={
        'machine_code': MACHINE_CODE, 'edition': 'official', 'max_cameras': '4', 'customer_id': 'acme',
    })
    page = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert '正式版必须填写到期日' in page
    assert 'value="acme"' in page
    assert client.get('/licenses/1.json', headers=AUTH).status_code == 404


def test_refuses_to_start_without_signing_key(db_path):
    with pytest.raises(RuntimeError):
        create_app({'SIGNING_KEY': '', 'DB_PATH': str(db_path)})
