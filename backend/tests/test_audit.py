import unittest
from app.services.audit import describe_operation


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

        review = describe_operation('PATCH', '/api/alerts/4/review', {'review_status': 'false_positive'})
        self.assertEqual(review['module'], '告警')
        self.assertIn('误报', review['summary'])

        power = describe_operation('POST', '/api/nodes/2/power', {'action': 'wake'})
        self.assertIn('唤醒', power['summary'])


if __name__ == '__main__':
    unittest.main()
