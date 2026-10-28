import unittest
import os
import json
import hashlib
from app import create_app
from app.services.config_service import ConfigService

class TestUserManagementAndSettings(unittest.TestCase):
    def setUp(self):
        os.environ['NETLENS_MASTER_KEY'] = 'test_master_key_sprint_10_10_0_super_secure='
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret'})
        self.client = self.app.test_client()
        
        # Load and back up original users
        ConfigService.reload_users()
        self.original_users = json.loads(json.dumps(ConfigService.load_users()))

    def tearDown(self):
        ConfigService.save_users(self.original_users)

    def login_as_admin(self):
        return self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)

    def test_multi_user_creation_and_login(self):
        # 1. Login as admin
        self.login_as_admin()

        # 2. List users
        res = self.client.get('/api/admin/users')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        usernames = [u['username'] for u in data['data']]
        self.assertIn('admin', usernames)

        # 3. Create operator user
        create_res = self.client.post('/api/admin/users', json={
            'username': 'operador_ti',
            'name': 'Operador de Rede',
            'password': 'safePassword123',
            'role': 'operator'
        })
        self.assertEqual(create_res.status_code, 201)

        # 4. Logout admin
        self.client.get('/logout')

        # 5. Login as new operator
        op_login = self.client.post('/login', data={
            'username': 'operador_ti',
            'password': 'safePassword123'
        }, follow_redirects=False)
        self.assertEqual(op_login.status_code, 302)

        # 6. Re-login as admin and update operator
        self.login_as_admin()
        up_res = self.client.put('/api/admin/users/operador_ti', json={
            'name': 'Operador Sênior'
        })
        self.assertEqual(up_res.status_code, 200)

        # 7. Delete operator user
        del_res = self.client.delete('/api/admin/users/operador_ti')
        self.assertEqual(del_res.status_code, 200)

        # 8. Prevent deleting active logged-in user
        self_del_res = self.client.delete('/api/admin/users/admin')
        self.assertEqual(self_del_res.status_code, 400)

    def test_database_settings_endpoints(self):
        self.login_as_admin()

        # GET db settings
        res = self.client.get('/api/settings/db')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('netdisco', data)
        self.assertIn('librenms', data)
        self.assertIn('zabbix', data)

        # POST db settings
        post_res = self.client.post('/api/settings/db', json={
            'netdisco': {'host': '192.168.10.51', 'port': 5432, 'database': 'netdisco', 'user': 'netdisco', 'password': 'pwd', 'type': 'postgresql'}
        })
        self.assertEqual(post_res.status_code, 200)
        self.assertTrue(post_res.get_json()['success'])

if __name__ == '__main__':
    unittest.main()
