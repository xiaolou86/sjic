import sys
import types
import unittest
from datetime import datetime, timedelta

# 路由模块会导入 cv2；单测只验证删库，不需要真实 OpenCV。
sys.modules.setdefault('cv2', types.ModuleType('cv2'))

import jwt
from flask import Flask
from sqlalchemy.pool import StaticPool

from app.extensions import db
from app.models import Alert, Camera, EdgeNode, Task
from app.routes.camera_routes import camera_bp
from config import Config


class TestDeleteCamera(unittest.TestCase):
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
        self.app.register_blueprint(camera_bp)
        with self.app.app_context():
            db.create_all()
            camera = Camera(name='门口', url='rtsp://example/live')
            db.session.add(camera)
            db.session.flush()
            node = EdgeNode(name='盒子', mac_address='aa:bb:cc:dd:ee:ff', bound_cameras=[camera.id])
            task = Task(name='检测', cameraId=camera.id, edge_node_id=None)
            db.session.add(node)
            db.session.add(task)
            db.session.flush()
            task.edge_node_id = node.id
            for _ in range(3):
                db.session.add(Alert(
                    camera_id=camera.id,
                    task_id=task.id,
                    alert_type='phone',
                    confidence=0.9,
                    image_url='edge_alert_keep.jpg',
                    timestamp=datetime.now(),
                ))
            db.session.commit()
            self.camera_id = camera.id
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

    def test_delete_camera_keeps_alerts_and_images(self):
        response = self.client.delete(f'/api/cameras/{self.camera_id}', headers=self.headers)
        self.assertEqual(response.status_code, 204, response.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNone(Camera.query.get(self.camera_id))
            alerts = Alert.query.order_by(Alert.id).all()
            self.assertEqual(len(alerts), 3)
            for alert in alerts:
                self.assertIsNone(alert.camera_id)
                self.assertIsNone(alert.task_id)
                self.assertEqual(alert.camera_name, '门口')
                self.assertEqual(alert.image_url, 'edge_alert_keep.jpg')
                self.assertEqual(alert.to_dict()['camera_name'], '门口')
            self.assertEqual(Task.query.filter_by(cameraId=self.camera_id).count(), 0)
            node = EdgeNode.query.first()
            self.assertEqual(node.bound_cameras, [])

    def test_unbinding_camera_stops_running_task(self):
        from app.services.detector import DetectorService

        with self.app.app_context():
            camera = Camera(name='侧位', url='rtsp://example/side')
            db.session.add(camera)
            db.session.flush()
            node = EdgeNode(name='盒子2', mac_address='11:22:33:44:55:66', bound_cameras=[camera.id])
            db.session.add(node)
            db.session.flush()
            running = Task(
                name='运行中',
                cameraId=camera.id,
                edge_node_id=node.id,
                status='running',
                run_status='running',
                schedule_start='08:00',
                schedule_end='18:00',
                schedule_paused=False,
            )
            scheduled = Task(
                name='定时未跑',
                cameraId=camera.id,
                edge_node_id=node.id,
                status='stopped',
                run_status='stopped',
                schedule_start='08:00',
                schedule_end='18:00',
                schedule_paused=False,
            )
            db.session.add_all([running, scheduled])
            db.session.commit()
            DetectorService().stop_tasks_for_unbound_cameras(node.id, [camera.id])
            running = Task.query.get(running.id)
            scheduled = Task.query.get(scheduled.id)
            self.assertEqual(running.status, 'stopped')
            self.assertEqual(running.run_status, 'stopped')
            self.assertTrue(running.schedule_paused)
            self.assertEqual(scheduled.status, 'stopped')
            self.assertTrue(scheduled.schedule_paused)
