import os
import unittest
from unittest import mock

from app.services.license_service import LicenseService

# Same vector as license-server/tests/test_signer.py, which issues these licenses.
SIGNED = {
    'edition': 'official',
    'customer_id': 'acme',
    'machine_code': 'abc123',
    'max_cameras': 16,
    'allowed_algorithms': ['b', 'a'],
    'issued_at': '2026-01-01',
    'expires_at': '2027-12-31',
    'signature': 'cfd1cb3fb6a9f24dead4573014e42faf05e55fe2dbe44481f0db1a8acaadc871',
}


class TestLicenseSignature(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'LICENSE_SIGNING_KEY': 'golden-test-key'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.svc = LicenseService()

    def test_accepts_license_server_signature(self):
        self.assertTrue(self.svc.verify_signature(SIGNED))

    def test_rejects_tampered_fields(self):
        self.assertFalse(self.svc.verify_signature({**SIGNED, 'max_cameras': 99}))
        self.assertFalse(self.svc.verify_signature({**SIGNED, 'expires_at': '2099-12-31'}))
