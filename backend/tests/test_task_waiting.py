import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.modules.setdefault('cv2', types.ModuleType('cv2'))

from flask import Flask
from sqlalchemy.pool import StaticPool

from app.extensions import db
from app.models import EdgeNode, Task
from app.services.detector import DetectorService
from app.services.mqtt_service import MqttService
from app.services.task_scheduler import _is_running_status

MAC = 'aa:bb:cc:dd:ee:01'


class TestTaskWaiting(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': StaticPool,
            'connect_args': {'check_same_thread': False},
        }
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        publish = mock.patch('app.services.mqtt_service.mqtt_service.publish_task_start')
        self.publish = publish.start()
        self.addCleanup(publish.stop)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _node(self, status='online', seconds_ago=5):
        node = EdgeNode(
            name='盒子',
            mac_address=MAC,
            status=status,
            last_heartbeat=datetime.now() - timedelta(seconds=seconds_ago),
        )
        db.session.add(node)
        db.session.commit()
        return node

    def _task(self, node, status='stopped'):
        task = Task(name='考场一', edge_node_id=node.id, status=status, run_status=status)
        db.session.add(task)
        db.session.commit()
        return task

    def test_offline_node_waits_without_publishing(self):
        for node_status, seconds_ago in (('offline', 5), ('online', 300)):
            with self.subTest(node_status=node_status, seconds_ago=seconds_ago):
                node = self._node(node_status, seconds_ago)
                task = self._task(node)
                result = DetectorService()._dispatch_start(task, node, {'task_id': task.id})
                self.assertTrue(result['success'])
                self.assertEqual(task.status, 'waiting')
                self.assertEqual(task.run_status, 'waiting')
                self.publish.assert_not_called()
                db.session.delete(task)
                db.session.delete(node)
                db.session.commit()

    def test_online_node_starts(self):
        node = self._node()
        task = self._task(node)
        DetectorService()._dispatch_start(task, node, {'task_id': task.id})
        self.assertEqual(task.status, 'starting')
        self.publish.assert_called_once_with(MAC, {'task_id': task.id})

    def test_waiting_task_counts_as_active_for_scheduler(self):
        self.assertTrue(_is_running_status('waiting'))

    def _heartbeat(self, status):
        service = MqttService()
        service.app = self.app
        service._handle_heartbeat({'edge_id': MAC, 'status': status, 'running_tasks': []})

    def test_online_heartbeat_starts_waiting_task(self):
        node = self._node('offline')
        task = self._task(node, status='waiting')
        with mock.patch.object(DetectorService, 'start_detection', return_value={'success': True}) as start:
            self._heartbeat('offline')
            start.assert_not_called()
            self.assertEqual(Task.query.get(task.id).status, 'waiting')

            self._heartbeat('online')
            start.assert_called_once_with(task.id)

    def test_waiting_task_stops_when_start_fails(self):
        node = self._node('offline')
        task = self._task(node, status='waiting')
        failed = {'success': False, 'message': 'License invalid'}
        with mock.patch.object(DetectorService, 'start_detection', return_value=failed):
            self._heartbeat('online')
        task = Task.query.get(task.id)
        self.assertEqual(task.status, 'stopped')
        self.assertEqual(task.run_status, 'stopped')


if __name__ == '__main__':
    unittest.main()
