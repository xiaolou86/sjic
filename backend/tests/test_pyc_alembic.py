import compileall
import shutil
import tempfile
import unittest
from pathlib import Path


class TestPycAlembic(unittest.TestCase):
    def test_legacy_pyc_revision_is_visible_after_loader(self):
        from alembic.config import Config
        from alembic.script.base import ScriptDirectory
        from app.utils.pyc_alembic import install_pyc_env_loader

        root = Path(tempfile.mkdtemp())
        original = ScriptDirectory.from_config
        ready = getattr(ScriptDirectory, '_sjic_env_ready', False)
        try:
            versions = root / 'versions'
            versions.mkdir()
            source = versions / '000_initial.py'
            source.write_text(
                'revision = "000"\n'
                'down_revision = None\n'
                'branch_labels = None\n'
                'depends_on = None\n'
                'def upgrade():\n'
                '    pass\n'
                'def downgrade():\n'
                '    pass\n',
                encoding='utf-8',
            )
            compileall.compile_file(str(source), legacy=True, quiet=1)
            source.unlink()
            ini = root / 'alembic.ini'
            ini.write_text('[alembic]\nscript_location = .\n', encoding='utf-8')

            plain = Config(str(ini))
            plain.set_main_option('script_location', str(root))
            self.assertEqual(ScriptDirectory.from_config(plain).get_heads(), [])

            install_pyc_env_loader()
            patched = Config(str(ini))
            patched.set_main_option('script_location', str(root))
            self.assertEqual(ScriptDirectory.from_config(patched).get_heads(), ['000'])
        finally:
            ScriptDirectory.from_config = original
            ScriptDirectory._sjic_env_ready = ready
            shutil.rmtree(root, ignore_errors=True)
