import unittest

from app.services.accounts import authenticate, hash_password


class TestAccounts(unittest.TestCase):
    def test_factory_password_until_changed(self):
        self.assertEqual(authenticate('admin', '123123', {}), 'customer')
        self.assertEqual(authenticate('super_admin', '123123', None), 'vendor')
        self.assertIsNone(authenticate('admin', 'wrong', {}))
        self.assertIsNone(authenticate('other', '123123', {}))

    def test_stored_hash_replaces_factory_password(self):
        config = {'accounts': {'admin': {'password_hash': hash_password('newpass1')}}}
        self.assertEqual(authenticate('admin', 'newpass1', config), 'customer')
        self.assertIsNone(authenticate('admin', '123123', config))
        self.assertEqual(authenticate('super_admin', '123123', config), 'vendor')


if __name__ == '__main__':
    unittest.main()
