import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.modules.setdefault('cv2', types.ModuleType('cv2'))

import jwt
from flask import Flask
from sqlalchemy.pool import StaticPool

import config as config_module
from app.extensions import db
from app.models import EdgeNode, Task
from app.routes.upgrade_routes import upgrade_bp
from config import Config


class TestUpgradeConstraints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.upgrades = os.path.join(self.tmp, 'upgrades')
        self.incoming = os.path.join(self.tmp, 'incoming')
        os.makedirs(self.upgrades)
        os.makedirs(self.incoming)
        patches = [
            mock.patch.dict(os.environ, {'SJIC_UPGRADES': self.upgrades, 'SJIC_INCOMING': self.incoming}),
            mock.patch('app.services.upgrade_service.read_version', return_value='1.2.0'),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        mqtt_patch = mock.patch('app.routes.upgrade_routes.mqtt_service')
        self.mqtt = mqtt_patch.start()
        self.addCleanup(mqtt_patch.stop)

        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.config['DOWNLOAD_SECURE_KEY'] = 'test-key'
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': StaticPool,
            'connect_args': {'check_same_thread': False},
        }
        db.init_app(self.app)
        self.app.register_blueprint(upgrade_bp)
        with self.app.app_context():
            db.create_all()
        token = jwt.encode(
            {'user': 'admin', 'role': 'customer', 'exp': datetime.utcnow() + timedelta(hours=1)},
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
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stage(self, component, version):
        filename = f'sjic-{component}-{version}.tar.gz'
        path = os.path.join(self.upgrades, filename)
        with open(path, 'wb') as handle:
            handle.write(b'package')
        meta = {'version': version, 'min_version': '1.0.0', 'filename': filename, 'sha256': '0' * 64, 'path': path}
        with open(os.path.join(self.upgrades, f'{component}.json'), 'w', encoding='utf-8') as handle:
            json.dump(meta, handle)

    def _node(self, mac, status='online', seconds_ago=5):
        with self.app.app_context():
            node = EdgeNode(
                name=f'盒子{mac[-2:]}',
                mac_address=mac,
                status=status,
                last_heartbeat=datetime.now() - timedelta(seconds=seconds_ago),
            )
            db.session.add(node)
            db.session.commit()
            return node.id

    def _task(self, name, node_id=None, status='running'):
        with self.app.app_context():
            db.session.add(Task(name=name, edge_node_id=node_id, status=status, run_status=status))
            db.session.commit()

    def _apply_platform(self):
        return self.client.post('/api/admin/upgrades/platform/apply', headers=self.headers)

    def _upgrade_node(self, node_id):
        return self.client.post(f'/api/nodes/{node_id}/upgrade', headers=self.headers)

    def test_platform_upgrade_refused_while_tasks_run(self):
        self._stage('platform', '1.3.0')
        self._task('考场一')
        self._task('考场二', status='stopped')
        response = self._apply_platform()
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        message = response.get_json()['error']
        self.assertIn('考场一', message)
        self.assertNotIn('考场二', message)
        self.assertFalse(os.path.exists(os.path.join(self.incoming, 'platform.request.json')))

    def test_platform_upgrade_requested_when_idle(self):
        self._stage('platform', '1.2.0')
        self._task('考场二', status='stopped')
        response = self._apply_platform()
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(os.path.exists(os.path.join(self.incoming, 'platform.request.json')))

    def test_platform_downgrade_refused(self):
        self._stage('platform', '1.1.9')
        response = self._apply_platform()
        self.assertEqual(response.status_code, 400)
        self.assertIn('不支持降级', response.get_json()['error'])

    def test_edge_upgrade_refused_when_node_offline(self):
        self._stage('edge', '1.2.0')
        offline = self._node('aa:aa:aa:aa:aa:01', status='offline')
        stale = self._node('aa:aa:aa:aa:aa:02', seconds_ago=300)
        for node_id in (offline, stale):
            response = self._upgrade_node(node_id)
            self.assertEqual(response.status_code, 400)
            self.assertIn('不在线', response.get_json()['error'])
        self.mqtt.publish_agent_upgrade.assert_not_called()

    def test_edge_upgrade_refused_while_node_tasks_run(self):
        self._stage('edge', '1.2.0')
        busy = self._node('aa:aa:aa:aa:aa:03')
        idle = self._node('aa:aa:aa:aa:aa:04')
        self._task('入场检测', node_id=busy)
        response = self._upgrade_node(busy)
        self.assertEqual(response.status_code, 400)
        self.assertIn('入场检测', response.get_json()['error'])
        response = self._upgrade_node(idle)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_edge_package_newer_than_platform_refused(self):
        self._stage('edge', '1.3.0')
        node_id = self._node('aa:aa:aa:aa:aa:05')
        response = self._upgrade_node(node_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('请先升级平台', response.get_json()['error'])

    def test_edge_upgrade_published(self):
        self._stage('edge', '1.1.0')
        node_id = self._node('aa:aa:aa:aa:aa:06')
        response = self._upgrade_node(node_id)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        args = self.mqtt.publish_agent_upgrade.call_args[0]
        self.assertEqual(args[0], 'aa:aa:aa:aa:aa:06')
        self.assertEqual(args[1]['version'], '1.1.0')
        with self.app.app_context():
            self.assertEqual(EdgeNode.query.get(node_id).upgrade_status, 'queued')


class TestSecretKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _load(self, env=None, yaml_cfg=None):
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch.object(config_module, 'default_sqlite_dir', self.tmp), \
                mock.patch.dict(config_module.yaml_cfg, yaml_cfg or {}, clear=True):
            if not env:
                os.environ.pop('SECRET_KEY', None)
            return config_module.load_secret_key()

    def test_generates_and_keeps_random_key(self):
        first = self._load()
        self.assertEqual(len(first), 64)
        self.assertEqual(self._load(), first)
        self.assertEqual(self._load(yaml_cfg={'app': {'secret_key': 'your-secret-key'}}), first)

    def test_configured_key_wins(self):
        self.assertEqual(self._load(env={'SECRET_KEY': 'from-env'}), 'from-env')
        self.assertEqual(self._load(yaml_cfg={'app': {'secret_key': 'from-yaml'}}), 'from-yaml')


if __name__ == '__main__':
    unittest.main()
