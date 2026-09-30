"""让 Alembic 在发版目录只有 .pyc 时仍能加载迁移。"""
import os


def install_pyc_revision_support():
    """versions/*.py 不存在时，改读同名 .pyc。"""
    try:
        from alembic.script.base import Script
    except ImportError:
        return
    if getattr(Script, '_sjic_pyc_ready', False):
        return
    original = getattr(Script, '_list_py_files', None)
    if original is None:
        return

    def _list_py_files(cls, dir_):
        paths = [os.path.abspath(path) for path in original(dir_)]
        seen = {os.path.splitext(os.path.basename(path))[0] for path in paths}
        try:
            names = os.listdir(dir_)
        except OSError:
            return iter(paths)
        for name in names:
            if not name.endswith('.pyc'):
                continue
            stem = name[:-4]
            if stem in seen:
                continue
            paths.append(os.path.abspath(os.path.join(dir_, name)))
            seen.add(stem)
        return iter(paths)

    Script._list_py_files = classmethod(_list_py_files)
    Script._sjic_pyc_ready = True


def install_pyc_env_loader():
    """flask db 固定加载 env.py。发版目录只有 env.pyc 时改走字节码。"""
    try:
        from alembic.script.base import ScriptDirectory
    except ImportError:
        return
    if getattr(ScriptDirectory, '_sjic_env_ready', False):
        return
    try:
        from alembic.util.pyfiles import load_python_file
    except ImportError:
        from alembic.util import load_python_file

    original = ScriptDirectory.run_env

    def run_env(self):
        install_pyc_revision_support()
        env_py = os.path.join(self.dir, 'env.py')
        env_pyc = os.path.join(self.dir, 'env.pyc')
        if (not os.path.isfile(env_py)) and os.path.isfile(env_pyc):
            load_python_file(self.dir, 'env.pyc')
            return None
        return original(self)

    ScriptDirectory.run_env = run_env
    ScriptDirectory._sjic_env_ready = True
