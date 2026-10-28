"""
Unit tests for integrated servers management (CRUD & Connectivity Testing).
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NETLENS_MASTER_KEY", "test_master_key_sprint_10_10_0_super_secure=")

from app import create_app
from app.services.config_service import ConfigService

class TestAdminServers(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

        # Snapshot do config para isolamento de teste
        import copy
        self._orig_config = copy.deepcopy(ConfigService.load_config())

    def tearDown(self):
        ConfigService.save_config(self._orig_config)
        ConfigService.reload_config()

    def test_get_admin_servers(self):
        """Test GET /api/admin/servers returns server list."""
        resp = self.client.get('/api/admin/servers')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('data'), list)
        self.assertTrue(len(data['data']) >= 4)
        names = [s['name'] for s in data['data']]
        self.assertIn('Netbox', names)
        self.assertIn('Zabbix', names)

    def test_create_and_delete_server(self):
        """Test POST and DELETE on /api/admin/servers."""
        payload = {
            "name": "Grafana NOC Test",
            "type": "generic",
            "url": "http://10.11.4.99:3000",
            "description": "Servidor de Teste",
            "show_in_header": True,
            "enabled": True
        }
        res = self.client.post('/api/admin/servers', json=payload)
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertTrue(created.get('success'))
        server_id = created['data']['id']

        # Verificar se está na lista
        get_res = self.client.get('/api/admin/servers')
        server_names = [s['name'] for s in get_res.get_json()['data']]
        self.assertIn("Grafana NOC Test", server_names)

        # Excluir o servidor
        del_res = self.client.delete(f'/api/admin/servers/{server_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json().get('success'))

        # Confirmar remoção
        get_res2 = self.client.get('/api/admin/servers')
        server_names2 = [s['name'] for s in get_res2.get_json()['data']]
        self.assertNotIn("Grafana NOC Test", server_names2)

    def test_update_server(self):
        """Test PUT /api/admin/servers/<id> updates existing server."""
        payload = {
            "name": "Proxmox Test",
            "type": "proxmox",
            "url": "https://10.11.0.250:8006",
            "show_in_header": True
        }
        res = self.client.post('/api/admin/servers', json=payload)
        self.assertEqual(res.status_code, 201)
        server_id = res.get_json()['data']['id']

        update_payload = {
            "name": "Proxmox Cluster Principal",
            "type": "proxmox",
            "url": "https://10.11.0.250:8006",
            "show_in_header": False
        }
        put_res = self.client.put(f'/api/admin/servers/{server_id}', json=update_payload)
        self.assertEqual(put_res.status_code, 200)
        self.assertTrue(put_res.get_json().get('success'))

        # Confirmar atualização
        get_res = self.client.get('/api/admin/servers')
        target = next((s for s in get_res.get_json()['data'] if s['id'] == server_id), None)
        self.assertIsNotNone(target)
        self.assertEqual(target['name'], "Proxmox Cluster Principal")
        self.assertFalse(target['show_in_header'])

        # Cleanup
        self.client.delete(f'/api/admin/servers/{server_id}')

    @patch('requests.get')
    def test_test_server_connection(self, mock_get):
        """Test POST /api/admin/servers/test tests connectivity."""
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_get.return_value = mock_res

        res = self.client.post('/api/admin/servers/test', json={"url": "http://192.168.10.50"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data['result']['online'])
        self.assertEqual(data['result']['status_code'], 200)

    def test_status_endpoint_includes_servers(self):
        """Test /api/status returns dynamic servers array."""
        res = self.client.get('/api/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('servers', data)
        self.assertIsInstance(data['servers'], list)
        self.assertTrue(len(data['servers']) >= 4)

if __name__ == '__main__':
    unittest.main()
