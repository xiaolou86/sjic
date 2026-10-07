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
from app.routes.edge_routes import edge_bp
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
        self.app.register_blueprint(edge_bp)
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

    def test_unbinding_camera_rejected_while_tasks_exist(self):
        with self.app.app_context():
            door = Camera(name='门口', url='rtsp://example/door')
            side = Camera(name='侧位', url='rtsp://example/side')
            db.session.add_all([door, side])
            db.session.flush()
            node = EdgeNode(
                name='盒子2',
                mac_address='11:22:33:44:55:66',
                bound_cameras=[door.id, side.id],
            )
            db.session.add(node)
            db.session.flush()
            db.session.add(Task(
                name='入场检测',
                cameraId=door.id,
                edge_node_id=node.id,
                status='running',
                run_status='running',
            ))
            db.session.add(Task(name='离座检测', cameraId=door.id, edge_node_id=node.id))
            db.session.commit()
            node_id = node.id
            door_id = door.id
            side_id = side.id

        blocked = self.client.put(
            f'/api/nodes/{node_id}',
            json={'name': '改名不应生效', 'bound_camera_ids': [side_id]},
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 400, blocked.get_data(as_text=True))
        message = blocked.get_json()['error']
        self.assertIn('门口', message)
        self.assertIn('入场检测', message)
        self.assertIn('离座检测', message)
        self.assertIn('请先到任务模块删除后再取消绑定', message)
        with self.app.app_context():
            node = EdgeNode.query.get(node_id)
            self.assertEqual(node.name, '盒子2')
            self.assertEqual(set(node.bound_cameras), {door_id, side_id})
            running = Task.query.filter_by(name='入场检测').one()
            self.assertEqual(running.status, 'running')
            for task in Task.query.filter_by(edge_node_id=node_id, cameraId=door_id).all():
                db.session.delete(task)
            db.session.commit()

        allowed = self.client.put(
            f'/api/nodes/{node_id}',
            json={'bound_camera_ids': [side_id]},
            headers=self.headers,
        )
        self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True))
        with self.app.app_context():
            node = EdgeNode.query.get(node_id)
            self.assertEqual(node.bound_cameras, [side_id])
