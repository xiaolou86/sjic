import sys
import types
import unittest
from datetime import datetime, timedelta

sys.modules.setdefault('cv2', types.ModuleType('cv2'))

import jwt
from flask import Flask
from sqlalchemy.pool import StaticPool

from app.extensions import db
from app.models.algorithm import Algorithm
from app.routes.dashboard_routes import dashboard_bp
from app.utils.algorithm_catalog import OD_SCENE_PRESETS, POSE_SCENE_PRESETS, detection_scene_count
from config import Config


def _token(role):
    token = jwt.encode(
        {'user': 'admin', 'role': role, 'exp': datetime.utcnow() + timedelta(hours=1)},
        Config.SECRET_KEY,
        algorithm='HS256',
    )
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return {'Authorization': f'Bearer {token}'}


class TestDashboardSceneCount(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': StaticPool,
            'connect_args': {'check_same_thread': False},
        }
        db.init_app(self.app)
        self.app.register_blueprint(dashboard_bp)
        with self.app.app_context():
            db.create_all()
            Algorithm.initialize_default_algorithms()
            db.session.add(Algorithm(
                name='目标检测（上架）',
                type='object_detection',
                engine='object_detection',
                category='exam',
                parameter_schema={
                    'origin': 'instance',
                    'scene_presets': list(OD_SCENE_PRESETS),
                    'publish_meta': {'published': True},
                },
            ))
            db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_scene_count_is_object_detection_plus_pose(self):
        expected = len(OD_SCENE_PRESETS) + len(POSE_SCENE_PRESETS)
        self.assertEqual(detection_scene_count(), expected)
        self.assertGreater(expected, 3)

        for role in ('vendor', 'customer'):
            response = self.client.get('/api/dashboard/summary', headers=_token(role))
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            counts = response.get_json()['counts']
            self.assertEqual(counts['algorithm_scenes'], expected)
            self.assertNotIn('algorithms', counts)
            self.assertNotIn('algorithms_listed', counts)
