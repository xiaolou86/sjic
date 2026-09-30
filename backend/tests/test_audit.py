import unittest
from app.services.audit import describe_operation, operation_visible_to, modules_for_role


class TestDescribeOperation(unittest.TestCase):
    def test_skips_reads_and_noise(self):
        self.assertIsNone(describe_operation('GET', '/api/cameras', {}))
        self.assertIsNone(describe_operation('POST', '/api/cameras/capture', {'camera_id': 1}))
        self.assertIsNone(describe_operation('POST', '/api/analytics/clicks', {'events': []}))
        self.assertIsNone(describe_operation('POST', '/api/edge/alerts', {}))

    def test_create_update_delete(self):
        created = describe_operation('POST', '/api/cameras', {'name': '门口'})
        self.assertEqual(created['action'], 'create')
        self.assertIn('门口', created['summary'])

        updated = describe_operation('PUT', '/api/tasks/3', {})
        self.assertEqual(updated['action'], 'update')
        self.assertIn('#3', updated['summary'])

        deleted = describe_operation('DELETE', '/api/algorithms/8', {})
        self.assertEqual(deleted['action'], 'delete')
        self.assertIn('#8', deleted['summary'])

    def test_login_logout_and_review(self):
        login = describe_operation('POST', '/api/login', {'username': 'admin', 'password': 'secret'})
        self.assertEqual(login['action'], 'login')
        self.assertNotIn('secret', login['summary'])
        self.assertEqual(login['username'], 'admin')

        logout = describe_operation('POST', '/api/logout', {})
        self.assertEqual(logout['action'], 'logout')

        changed = describe_operation('POST', '/api/auth/password', {
            'old_password': 'secret',
            'new_password': 'secret2',
        })
        self.assertEqual(changed['summary'], '修改登录密码')
        self.assertNotIn('secret', changed['summary'])

        review = describe_operation('PATCH', '/api/alerts/4/review', {'review_status': 'false_positive'})
        self.assertEqual(review['module'], '告警')
        self.assertIn('误报', review['summary'])

        power = describe_operation('POST', '/api/nodes/2/power', {'action': 'wake'})
        self.assertIn('唤醒', power['summary'])

        upgrade = describe_operation('POST', '/api/nodes/5/upgrade', {})
        self.assertEqual(upgrade['module'], '节点')
        self.assertIn('#5', upgrade['summary'])

    def test_customer_cannot_see_super_admin_or_vendor_modules(self):
        self.assertFalse(operation_visible_to('customer', 'super_admin', 'vendor', '节点'))
        self.assertFalse(operation_visible_to('customer', 'super_admin', '', '认证'))
        self.assertFalse(operation_visible_to('customer', 'admin', 'vendor', '视频源'))
        self.assertFalse(operation_visible_to('customer', 'admin', 'customer', '模型'))
        self.assertFalse(operation_visible_to('customer', 'admin', 'customer', '训练'))
        self.assertTrue(operation_visible_to('customer', 'admin', 'customer', '告警'))
        self.assertTrue(operation_visible_to('vendor', 'super_admin', 'vendor', '模型'))
        self.assertNotIn('模型', modules_for_role('customer'))
        self.assertNotIn('训练', modules_for_role('customer'))
        self.assertIn('模型', modules_for_role('vendor'))


if __name__ == '__main__':
    unittest.main()
