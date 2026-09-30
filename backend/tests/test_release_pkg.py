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
