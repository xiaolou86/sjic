import os
import tempfile
import unittest

from sqlalchemy import create_engine, event, text

from app.utils.db_compat import apply_sqlite_pragmas
from app.utils.serve_process import should_start_background_services


class TestSqlitePragmas(unittest.TestCase):
    def test_wal_and_busy_timeout(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        uri = 'sqlite:///' + path.replace('\\', '/')
        engine = create_engine(uri, connect_args={'timeout': 30})
        event.listen(engine, 'connect', apply_sqlite_pragmas)
        try:
            with engine.connect() as conn:
                mode = conn.execute(text('PRAGMA journal_mode')).scalar()
                timeout = conn.execute(text('PRAGMA busy_timeout')).scalar()
            self.assertEqual(str(mode).lower(), 'wal')
            self.assertEqual(int(timeout), 30000)
        finally:
            engine.dispose()
            for suffix in ('', '-wal', '-shm'):
                try:
                    os.remove(path + suffix)
                except OSError:
                    pass


class TestServeProcess(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('SJIC_RELOADER', None)
        os.environ.pop('WERKZEUG_RUN_MAIN', None)

    def test_reloader_parent_skips_workers(self):
        os.environ['SJIC_RELOADER'] = '1'
        os.environ.pop('WERKZEUG_RUN_MAIN', None)
        self.assertFalse(should_start_background_services())

    def test_reloader_child_and_production_start_workers(self):
        os.environ['SJIC_RELOADER'] = '1'
        os.environ['WERKZEUG_RUN_MAIN'] = 'true'
        self.assertTrue(should_start_background_services())

        os.environ.pop('SJIC_RELOADER', None)
        os.environ.pop('WERKZEUG_RUN_MAIN', None)
        self.assertTrue(should_start_background_services())
