import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path


def _load_verify():
    path = Path(__file__).resolve().parents[2] / 'deploy' / 'verify_release.py'
    spec = importlib.util.spec_from_file_location('sjic_verify_release', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = _load_verify()


class TestReleasePackage(unittest.TestCase):
    def _archive(self, files, version='1.2.0', min_version='1.0.0'):
        root = Path(tempfile.mkdtemp())
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, bytes) else content.encode('utf-8')
            path.write_bytes(data)
        records = []
        for path in sorted(root.rglob('*')):
            if path.is_file():
                records.append({
                    'path': path.relative_to(root).as_posix(),
                    'sha256': verify.sha256_file(str(path)),
                })
        manifest = verify.build_manifest({
            'component': 'edge',
            'version': version,
            'min_version': min_version,
            'python': '3.10',
            'files': records,
        })
        (root / 'manifest.json').write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for path in root.rglob('*'):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(root).as_posix())
        shutil.rmtree(root, ignore_errors=True)
        return buffer.getvalue()

    def _write_blob(self, blob):
        handle = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
        handle.write(blob)
        handle.close()
        return handle.name

    def test_frontend_build_manifest_is_listed(self):
        import importlib.util
        module_path = Path(__file__).resolve().parents[2] / 'deploy' / 'build_release.py'
        spec = importlib.util.spec_from_file_location('sjic_build_release', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path(tempfile.mkdtemp())
        try:
            nested = root / 'frontend' / 'build' / 'manifest.json'
            nested.parent.mkdir(parents=True)
            nested.write_text('{"files":{}}', encoding='utf-8')
            (root / 'install.sh').write_text('echo ok\n', encoding='utf-8')
            listed = {item['path'] for item in module.file_records(root)}
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertIn('frontend/build/manifest.json', listed)
        self.assertIn('install.sh', listed)

    def test_whitelist_skips_extras_and_rejects_backup_files(self):
        module_path = Path(__file__).resolve().parents[2] / 'deploy' / 'build_release.py'
        spec = importlib.util.spec_from_file_location('sjic_build_release', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        src = Path(tempfile.mkdtemp())
        out = Path(tempfile.mkdtemp())
        try:
            (src / 'app' / 'cmd').mkdir(parents=True)
            (src / 'app' / 'models').mkdir()
            (src / 'app' / 'main.py').write_text('x', encoding='utf-8')
            (src / 'app' / 'models' / 'task.py').write_text('x', encoding='utf-8')
            (src / 'app' / 'cmd' / 'debug.py').write_text('x', encoding='utf-8')
            (src / 'images').mkdir()
            (src / 'images' / 'calibration_2.jpg').write_bytes(b'x')
            (src / 'config.yaml').write_text('secret', encoding='utf-8')
            module.copy_tree(src, out / 'a', ('app',), {('app', 'cmd')})
            copied = sorted(p.relative_to(out / 'a').as_posix() for p in (out / 'a').rglob('*') if p.is_file())
            self.assertEqual(copied, ['app/main.py', 'app/models/task.py'])
            self.assertIn('entrypoint.sh', module.EDGE_ENTRIES)

            (src / 'app' / 'routes.py.bak').write_text('x', encoding='utf-8')
            with self.assertRaises(SystemExit):
                module.copy_tree(src, out / 'b', ('app',), {('app', 'cmd')})
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(out, ignore_errors=True)

    def test_compile_tree_removes_python_source(self):
        module_path = Path(__file__).resolve().parents[2] / 'deploy' / 'build_release.py'
        spec = importlib.util.spec_from_file_location('sjic_build_release_compile', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path(tempfile.mkdtemp())
        try:
            package = root / 'pkg'
            package.mkdir()
            (package / '__init__.py').write_text('VALUE = 1\n', encoding='utf-8')
            (root / 'main.py').write_text('from pkg import VALUE\n', encoding='utf-8')
            (root / 'entrypoint.sh').write_bytes(b'#!/bin/sh\r\nset -e\r\n')
            module.compile_tree(root)
            files = sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob('*')
                if path.is_file()
            )
            self.assertEqual(files, ['entrypoint.sh', 'main.pyc', 'pkg/__init__.pyc'])
            dest = Path(tempfile.mkdtemp())
            try:
                module.copy_tree(root, dest, ('entrypoint.sh',))
                self.assertEqual((dest / 'entrypoint.sh').read_bytes(), b'#!/bin/sh\nset -e\n')
            finally:
                shutil.rmtree(dest, ignore_errors=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        broken = Path(tempfile.mkdtemp())
        try:
            (broken / 'bad.py').write_text('def (\n', encoding='utf-8')
            with self.assertRaises(SystemExit):
                module.compile_tree(broken)
        finally:
            shutil.rmtree(broken, ignore_errors=True)

    def test_accepts_pyc_package(self):
        path = self._write_blob(self._archive({
            'install.sh': '#!/bin/bash\necho ok\n',
            'VERSION': '1.2.0\n',
            'edge-agent/main.pyc': b'\x00pyc',
        }))
        try:
            manifest = verify.verify_tarball(path, current_version='1.1.0')
        finally:
            os.remove(path)
        self.assertEqual(manifest['version'], '1.2.0')

    def test_rejects_python_source_and_bad_checksum(self):
        source_path = self._write_blob(self._archive({'install.sh': 'echo ok\n', 'app.py': 'print(1)\n'}))
        try:
            with self.assertRaises(verify.ReleaseError):
                verify.verify_tarball(source_path)
        finally:
            os.remove(source_path)

        good = self._archive({'install.sh': 'echo ok\n', 'edge-agent/main.pyc': b'\x00'})
        checksum_path = self._write_blob(good)
        try:
            with self.assertRaises(verify.ReleaseError):
                verify.verify_tarball(checksum_path, expected_sha256='0' * 64)
        finally:
            os.remove(checksum_path)

    def test_version_floor(self):
        self.assertTrue(verify.version_gte('1.2.0', '1.2.0'))
        self.assertTrue(verify.version_gte('1.0.0', '1.0.0'))
        self.assertFalse(verify.version_gte('1.0.0', '1.2.0'))
        path = self._write_blob(self._archive(
            {'install.sh': 'echo ok\n', 'edge-agent/main.pyc': b'\x00'},
            min_version='1.2.0',
        ))
        try:
            with self.assertRaises(verify.ReleaseError):
                verify.verify_tarball(path, current_version='1.0.0')
        finally:
            os.remove(path)


if __name__ == '__main__':
    unittest.main()
