import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# 没装 OpenCV 时用空模块代替，避免把已经安装的 cv2/numpy 挡掉。
for _name in ('cv2', 'numpy'):
    if _name in sys.modules:
        continue
    try:
        __import__(_name)
    except ImportError:
        sys.modules[_name] = types.ModuleType(_name)

import jwt
from flask import Flask
from sqlalchemy.pool import StaticPool

from app.extensions import db
from app.models import Alert
from app.routes.alert_routes import alert_bp
from app.routes.edge_routes import edge_bp
from app.utils.alert_images import (
    alert_file_path,
    allocate_alert_relpath,
    companion_raw_rel,
    delete_stored_images,
    is_managed_alert_name,
    main,
    run_cleanup,
    safe_relative,
    save_alert_upload,
)
from config import Config


def _quiet(*_args, **_kwargs):
    return None


def _touch(path, age_seconds=None, payload=b'img'):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(payload)
    if age_seconds is not None:
        stamp = datetime.now().timestamp() - age_seconds
        os.utime(path, (stamp, stamp))


def _db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE alerts (id INTEGER PRIMARY KEY, timestamp TEXT, image_url TEXT)')
    conn.executemany(
        'INSERT INTO alerts (id, timestamp, image_url) VALUES (?, ?, ?)',
        rows,
    )
    conn.commit()
    conn.close()


class TestAlertImagePaths(unittest.TestCase):
    def test_new_images_go_into_an_hour_directory(self):
        rel = allocate_alert_relpath(when=datetime(2026, 10, 21, 18, 14, 30, 123456))
        self.assertEqual(rel, '2026/10/21/18/edge_alert_20261021_181430_123456.jpg')
        self.assertTrue(is_managed_alert_name(os.path.basename(rel)))
        self.assertTrue(is_managed_alert_name('edge_alert_20261021_181430_123456_raw.jpg'))
        self.assertFalse(is_managed_alert_name('vacation.jpg'))

    def test_relative_path_cannot_escape_the_alert_directory(self):
        self.assertEqual(safe_relative('2026/10/21/18/a.jpg'), '2026/10/21/18/a.jpg')
        self.assertEqual(safe_relative('/api/alerts/images/2026/10/21/18/a.jpg'), '2026/10/21/18/a.jpg')
        self.assertIsNone(safe_relative('../secret.jpg'))
        self.assertIsNone(safe_relative('C:/secret.jpg'))
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'alerts')
            os.makedirs(folder)
            secret = os.path.join(root, 'secret.jpg')
            _touch(secret)
            self.assertIsNone(alert_file_path(folder, '../secret.jpg'))
            resolved = alert_file_path(folder, '/etc/passwd')
            root_real = os.path.realpath(folder)
            self.assertEqual(os.path.commonpath([root_real, resolved]), root_real)
            self.assertTrue(os.path.isfile(secret))

    def test_save_writes_annotated_and_raw_under_the_hour(self):
        class Blob:
            def __init__(self, data):
                self._data = data

            def save(self, path):
                with open(path, 'wb') as handle:
                    handle.write(self._data)

        with tempfile.TemporaryDirectory() as folder:
            rel = save_alert_upload(
                folder,
                Blob(b'annotated'),
                Blob(b'raw'),
                when=datetime(2026, 10, 21, 18, 0, 0, 1),
            )
            self.assertEqual(rel, '2026/10/21/18/edge_alert_20261021_180000_000001.jpg')
            annotated = os.path.join(folder, *rel.split('/'))
            raw = os.path.join(folder, *companion_raw_rel(rel).split('/'))
            self.assertEqual(open(annotated, 'rb').read(), b'annotated')
            self.assertEqual(open(raw, 'rb').read(), b'raw')
            self.assertEqual(os.listdir(folder), ['2026'])

    def test_delete_removes_both_files_and_empty_hour_dirs(self):
        with tempfile.TemporaryDirectory() as folder:
            rel = '2026/10/21/18/edge_alert_20261021_180000_000001.jpg'
            _touch(os.path.join(folder, *rel.split('/')))
            _touch(os.path.join(folder, *companion_raw_rel(rel).split('/')))
            removed = delete_stored_images(folder, rel, log=_quiet)
            self.assertEqual(removed, 2)
            self.assertEqual(os.listdir(folder), [])


class TestAlertCleanup(unittest.TestCase):
    def test_dry_run_then_apply_purges_relocates_and_drops_orphans(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'alerts')
            os.makedirs(folder)
            db_path = os.path.join(root, 'app.db')
            secret = os.path.join(root, 'secret.jpg')
            _touch(secret, age_seconds=86400)
            old_name = 'edge_alert_20260101_010101_000001.jpg'
            keep_name = 'edge_alert_20261021_181430_000002.jpg'
            orphan_name = 'edge_alert_20260202_020202_000003.jpg'
            recent_name = 'edge_alert_20261021_190000_000004.jpg'
            _touch(os.path.join(folder, old_name), age_seconds=86400)
            _touch(os.path.join(folder, 'edge_alert_20260101_010101_000001_raw.jpg'), age_seconds=86400)
            _touch(os.path.join(folder, keep_name), age_seconds=86400)
            _touch(os.path.join(folder, 'edge_alert_20261021_181430_000002_raw.jpg'), age_seconds=86400)
            _touch(os.path.join(folder, orphan_name), age_seconds=86400)
            _touch(os.path.join(folder, recent_name))
            _touch(os.path.join(folder, 'vacation.jpg'), age_seconds=86400)
            _db(db_path, [
                (1, '2026-01-01 01:01:01', old_name),
                (2, '2026-10-21 18:14:30', keep_name),
                (3, '2026-01-15 00:00:00', '../secret.jpg'),
            ])
            kwargs = dict(
                before=datetime(2026, 9, 1),
                relocate=True,
                remove_orphans=True,
                log=_quiet,
            )
            preview = run_cleanup(db_path, folder, apply=False, **kwargs)
            self.assertEqual(preview['purge_alerts'], 2)
            self.assertEqual(preview['relocate_alerts'], 1)
            self.assertEqual(preview['orphan_files'], 1)
            self.assertTrue(os.path.isfile(os.path.join(folder, old_name)))
            self.assertTrue(os.path.isfile(secret))

            result = run_cleanup(db_path, folder, apply=True, **kwargs)
            self.assertEqual(result['purge_alerts'], 2)
            self.assertEqual(result['purge_files'], 2)
            self.assertEqual(result['relocate_files'], 2)
            self.assertFalse(os.path.isfile(os.path.join(folder, old_name)))
            self.assertTrue(os.path.isfile(secret))
            kept = '2026/10/21/18/edge_alert_20261021_181430_000002.jpg'
            self.assertTrue(os.path.isfile(os.path.join(folder, *kept.split('/'))))
            self.assertTrue(os.path.isfile(os.path.join(
                folder, *companion_raw_rel(kept).split('/')
            )))
            self.assertFalse(os.path.isfile(os.path.join(folder, orphan_name)))
            self.assertTrue(os.path.isfile(os.path.join(folder, recent_name)))
            self.assertTrue(os.path.isfile(os.path.join(folder, 'vacation.jpg')))
            conn = sqlite3.connect(db_path)
            rows = conn.execute('SELECT id, image_url FROM alerts ORDER BY id').fetchall()
            conn.close()
            self.assertEqual(rows, [(2, kept)])

    def test_limit_stops_after_one_row_and_rerun_continues(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, 'app.db')
            alerts = os.path.join(folder, 'alerts')
            os.makedirs(alerts)
            rows = []
            for index in range(1, 4):
                name = f'edge_alert_2026010{index}_010101_00000{index}.jpg'
                _touch(os.path.join(alerts, name))
                rows.append((index, f'2026-01-0{index} 01:01:01', name))
            _db(db_path, rows)
            first = run_cleanup(
                db_path, alerts, before=datetime(2026, 9, 1), apply=True, limit=1, log=_quiet,
            )
            self.assertEqual(first['purge_alerts'], 1)
            conn = sqlite3.connect(db_path)
            left = conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
            conn.close()
            self.assertEqual(left, 2)
            second = run_cleanup(
                db_path, alerts, before=datetime(2026, 9, 1), apply=True, log=_quiet,
            )
            self.assertEqual(second['purge_alerts'], 2)

    def test_relocate_recovers_when_the_file_was_already_moved(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, 'app.db')
            name = 'edge_alert_20260102_031500_000001.jpg'
            dest = os.path.join(folder, '2026', '01', '02', '03', name)
            _touch(dest)
            _db(db_path, [(1, '2026-01-02 03:15:00', name)])
            result = run_cleanup(db_path, folder, relocate=True, apply=True, log=_quiet)
            self.assertEqual(result['relocate_alerts'], 1)
            self.assertEqual(result['relocate_files'], 0)
            conn = sqlite3.connect(db_path)
            stored = conn.execute('SELECT image_url FROM alerts').fetchone()[0]
            conn.close()
            self.assertEqual(stored, f'2026/01/02/03/{name}')
            self.assertTrue(os.path.isfile(dest))

    def test_command_defaults_to_a_dry_run(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, 'app.db')
            name = 'edge_alert_20260101_010101_000001.jpg'
            _touch(os.path.join(folder, name))
            _db(db_path, [(1, '2026-01-01 01:01:01', name)])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(['--db', db_path, '--dir', folder, '--before', '2026-09-01'])
            self.assertEqual(code, 0)
            self.assertIn('这是统计，没有删除或移动文件。确认后追加 --apply', buf.getvalue())
            self.assertTrue(os.path.isfile(os.path.join(folder, name)))
            self.assertEqual(main(['--db', db_path, '--dir', folder]), 2)


class TestAlertImageRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': StaticPool,
            'connect_args': {'check_same_thread': False},
        }
        self.app.config['ALERT_FOLDER'] = self.tmp.name
        db.init_app(self.app)
        self.app.register_blueprint(alert_bp)
        self.app.register_blueprint(edge_bp)
        with self.app.app_context():
            db.create_all()
        token = jwt.encode(
            {
                'user': 'admin',
                'role': 'customer',
                'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            },
            Config.SECRET_KEY,
            algorithm='HS256',
        )
        if isinstance(token, bytes):
            token = token.decode('utf-8')
        self.client = self.app.test_client()
        self.headers = {'Authorization': f'Bearer {token}'}

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.tmp.cleanup()

    def test_edge_upload_stores_hour_path(self):
        data = {
            'alert_type': 'phone',
            'confidence': '0.9',
            'image': (io.BytesIO(b'annotated'), 'a.jpg'),
            'raw_image': (io.BytesIO(b'raw'), 'b.jpg'),
        }
        with patch('app.routes.edge_routes.socketio.emit'):
            response = self.client.post(
                '/api/edge/alerts',
                data=data,
                content_type='multipart/form-data',
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with self.app.app_context():
            alert = Alert.query.one()
            rel = alert.image_url
            self.assertRegex(rel, r'^\d{4}/\d{2}/\d{2}/\d{2}/edge_alert_\d{8}_\d{6}_\d+\.jpg$')
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, *rel.split('/'))))
        raw = companion_raw_rel(rel)
        self.assertEqual(open(os.path.join(self.tmp.name, *raw.split('/')), 'rb').read(), b'raw')
        self.assertFalse(any(name.endswith('.jpg') for name in os.listdir(self.tmp.name)))

    def test_delete_alert_removes_flat_files(self):
        name = 'edge_alert_20260101_010101_000001.jpg'
        raw = 'edge_alert_20260101_010101_000001_raw.jpg'
        _touch(os.path.join(self.tmp.name, name))
        _touch(os.path.join(self.tmp.name, raw))
        with self.app.app_context():
            alert = Alert(alert_type='phone', confidence=0.5, image_url=name, timestamp=datetime.now())
            db.session.add(alert)
            db.session.commit()
            alert_id = alert.id
        response = self.client.delete(f'/api/alerts/{alert_id}', headers=self.headers)
        self.assertEqual(response.status_code, 204, response.get_data(as_text=True))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, name)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, raw)))
        with self.app.app_context():
            self.assertIsNone(Alert.query.get(alert_id))

    def test_nested_image_is_served_and_raw_is_hidden(self):
        rel = '2026/10/21/18/edge_alert_20261021_181430_123456.jpg'
        _touch(os.path.join(self.tmp.name, *rel.split('/')), payload=b'annotated')
        raw = companion_raw_rel(rel)
        _touch(os.path.join(self.tmp.name, *raw.split('/')), payload=b'raw')
        shown = self.client.get('/api/alerts/images/' + rel)
        hidden = self.client.get('/api/alerts/images/' + raw)
        self.assertEqual(shown.status_code, 200)
        self.assertEqual(shown.data, b'annotated')
        self.assertEqual(hidden.status_code, 404)

    def test_export_includes_nested_raw_image(self):
        rel = '2026/10/21/18/edge_alert_20261021_181430_123456.jpg'
        _touch(os.path.join(self.tmp.name, *rel.split('/')), payload=b'annotated')
        _touch(os.path.join(self.tmp.name, *companion_raw_rel(rel).split('/')), payload=b'raw')
        with self.app.app_context():
            alert = Alert(alert_type='phone', confidence=0.5, image_url=rel, timestamp=datetime.now())
            db.session.add(alert)
            db.session.commit()
            alert_id = alert.id
        response = self.client.post(
            '/api/alerts/export',
            json={'ids': [alert_id]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content_type)
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        names = archive.namelist()
        self.assertIn(f'images/{alert_id}_edge_alert_20261021_181430_123456.jpg', names)
        self.assertIn(f'images/{alert_id}_edge_alert_20261021_181430_123456_raw.jpg', names)
        self.assertEqual(
            archive.read(f'images/{alert_id}_edge_alert_20261021_181430_123456_raw.jpg'),
            b'raw',
        )


if __name__ == '__main__':
    unittest.main()
