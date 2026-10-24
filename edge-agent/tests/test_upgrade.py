import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import utils.upgrade as upgrade  # noqa: E402

CONFIG = {'platform': {'api_base_url': 'http://10.0.0.5:38881/api/edge'}}


class _Reporter:
    def __init__(self):
        self.reports = []

    def publish_upgrade_status(self, status, message='', version=''):
        self.reports.append((status, message))


class _Response:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.content


class TestResolveDownloadUrl(unittest.TestCase):
    def test_relative_path_goes_to_platform(self):
        url = upgrade.resolve_download_url(CONFIG, '/static-upgrades/a.tar.gz?md5=x')
        self.assertEqual(url, 'http://10.0.0.5:38880/static-upgrades/a.tar.gz?md5=x')

    def test_absolute_url_must_be_platform_host(self):
        same = 'http://10.0.0.5:38880/static-upgrades/a.tar.gz'
        self.assertEqual(upgrade.resolve_download_url(CONFIG, same), same)
        with self.assertRaises(ValueError):
            upgrade.resolve_download_url(CONFIG, 'http://10.0.0.99/evil.tar.gz')


class TestRunUpgrade(unittest.TestCase):
    def setUp(self):
        self.incoming = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.incoming, True)
        for name, value in (
            ('INCOMING', self.incoming),
            ('HOST_STATUS', os.path.join(self.incoming, 'edge.status.json')),
            ('READY_FILE', os.path.join(self.incoming, 'edge.ready')),
        ):
            patch = mock.patch.object(upgrade, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.reporter = _Reporter()
        self.tasks = types.SimpleNamespace(active_tasks={})
        self.content = b'edge package'
        self.data = {
            'version': '1.2.0',
            'sha256': hashlib.sha256(self.content).hexdigest(),
            'url': '/static-upgrades/sjic-edge-1.2.0.tar.gz',
        }

    def _write_status(self, state, message):
        with open(upgrade.HOST_STATUS, 'w', encoding='utf-8') as handle:
            json.dump({'state': state, 'version': '1.2.0', 'message': message}, handle)

    def _run(self, host_script):
        with mock.patch.object(upgrade.requests, 'get', return_value=_Response(self.content)), \
                mock.patch.object(upgrade.subprocess, 'run', side_effect=host_script), \
                mock.patch.object(upgrade.time, 'sleep'):
            upgrade.run_upgrade(self.reporter, CONFIG, self.tasks, self.data)

    def test_refuses_while_tasks_run(self):
        self.tasks.active_tasks = {7: object()}
        with mock.patch.object(upgrade.requests, 'get') as get:
            upgrade.run_upgrade(self.reporter, CONFIG, self.tasks, self.data)
        get.assert_not_called()
        self.assertEqual(self.reporter.reports[-1][0], 'failed')
        self.assertIn('任务在运行', self.reporter.reports[-1][1])

    def test_reports_host_verify_failure(self):
        self._write_status('failed', '上一次的失败')

        def host_script(command, **kwargs):
            self._write_status('failed', '安装包校验失败')
            return subprocess.CompletedProcess(command, 1)

        self._run(host_script)
        self.assertEqual(self.reporter.reports[-1], ('failed', '安装包校验失败'))

    def test_reports_failure_after_handoff(self):
        def host_script(command, **kwargs):
            self._write_status('failed', '磁盘剩余 100 MB，至少需要 500 MB，未做任何改动')
            return subprocess.CompletedProcess(command, 0)

        self._run(host_script)
        self.assertEqual(self.reporter.reports[-1][0], 'failed')
        self.assertIn('磁盘剩余', self.reporter.reports[-1][1])

    def test_removes_old_packages(self):
        old = os.path.join(self.incoming, 'sjic-edge-1.1.0.tar.gz')
        Path(old).write_bytes(b'old')

        def host_script(command, **kwargs):
            self._write_status('success', '')
            return subprocess.CompletedProcess(command, 0)

        self._run(host_script)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(os.path.join(self.incoming, 'sjic-edge-1.2.0.tar.gz')))

    def test_write_ready_uses_agent_version(self):
        upgrade.write_ready()
        with open(upgrade.READY_FILE, encoding='utf-8') as handle:
            self.assertEqual(handle.read().strip(), upgrade.read_version())


class TestTaskStartDuringUpgrade(unittest.TestCase):
    def setUp(self):
        stub = types.ModuleType('engine.task_manager')
        stub.TaskManager = object
        with mock.patch.dict(sys.modules, {'engine.task_manager': stub}):
            sys.modules.pop('mqtt_client', None)
            import mqtt_client
        self.addCleanup(sys.modules.pop, 'mqtt_client', None)
        self.task_manager = mock.Mock()
        config = {'edge_id': 'aa:bb', 'mqtt': {'broker_url': '127.0.0.1', 'broker_port': 1883}}
        self.client = mqtt_client.EdgeMqttClient(config, self.task_manager)
        self.client.client = mock.Mock()

    def _start_message(self):
        payload = json.dumps({'task_id': 9}).encode('utf-8')
        return types.SimpleNamespace(topic='sjic/edge/aa:bb/task/start', payload=payload)

    def test_rejects_start_while_upgrading(self):
        self.client.upgrading = True
        self.client.on_message(None, None, self._start_message())
        self.task_manager.start_task.assert_not_called()
        topic, body = self.client.client.publish.call_args[0][:2]
        self.assertTrue(topic.endswith('/task/status'))
        self.assertEqual(json.loads(body)['status'], 'stopped')

    def test_starts_task_otherwise(self):
        self.client.on_message(None, None, self._start_message())
        self.task_manager.start_task.assert_called_once()


if __name__ == '__main__':
    unittest.main()
