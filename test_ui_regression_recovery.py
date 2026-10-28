import unittest
import threading
from app import create_app
from app.services.config_service import ConfigService
from app.analysis.ping_monitor import PingMonitor
from app.routes.alerts import ping_monitor as global_ping_monitor

class TestUIRegressionRecovery(unittest.TestCase):

    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user'] = 'admin'

    def test_links_endpoint_contains_all_four_systems(self):
        """Test GET /api/links contains NetBox, Netdisco, LibreNMS, and Zabbix with valid URLs."""
        res = self.client.get('/api/links')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertIsInstance(data, list)
        
        system_names = [item['name'] for item in data]
        self.assertIn('NetBox', system_names)
        self.assertIn('Netdisco', system_names)
        self.assertIn('LibreNMS', system_names)
        self.assertIn('Zabbix', system_names)

        urls = {item['name']: item['url'] for item in data}
        self.assertEqual(urls['NetBox'], 'https://192.168.10.235/')
        self.assertEqual(urls['Netdisco'], 'http://192.168.10.51:5000')
        self.assertEqual(urls['LibreNMS'], 'http://192.168.10.50:8000/')
        self.assertEqual(urls['Zabbix'], 'http://192.168.10.108')

    def test_status_endpoint_contains_urls_and_netbox(self):
        """Test GET /api/status returns urls dict matching frontend expectations."""
        res = self.client.get('/api/status')
        self.assertEqual(res.status_code, 200)
        data = res.json
        
        self.assertIn('urls', data)
        urls = data['urls']
        self.assertEqual(urls.get('netbox'), 'https://192.168.10.235/')
        self.assertEqual(urls.get('netdisco'), 'http://192.168.10.51:5000')
        self.assertEqual(urls.get('librenms'), 'http://192.168.10.50:8000/')
        self.assertEqual(urls.get('zabbix'), 'http://192.168.10.108')
        self.assertIn('netbox', data)

    def test_ping_monitor_idempotent_start(self):
        """Test calling PingMonitor.start() multiple times creates only 1 thread."""
        pm = PingMonitor(simulation_mode=True)
        pm.running = False
        
        # Call start 3 times
        pm.start()
        thread_1 = pm.thread
        pm.start()
        thread_2 = pm.thread
        pm.start()
        thread_3 = pm.thread
        
        self.assertTrue(pm.running)
        self.assertIs(thread_1, thread_2)
        self.assertIs(thread_2, thread_3)
        self.assertTrue(thread_1.is_alive())
        
        pm.stop()
        self.assertFalse(pm.running)

    def test_ping_monitor_stop(self):
        """Test PingMonitor.stop() stops the running thread safely."""
        pm = PingMonitor(simulation_mode=True)
        pm.start()
        self.assertTrue(pm.running)
        pm.stop()
        self.assertFalse(pm.running)

    def test_create_app_multiple_calls_no_thread_duplication(self):
        """Test calling create_app multiple times does not spawn duplicate ping_monitor threads."""
        app1 = create_app({'TESTING': True})
        thread_after_1 = global_ping_monitor.thread
        
        app2 = create_app({'TESTING': True})
        thread_after_2 = global_ping_monitor.thread
        
        app3 = create_app({'TESTING': True})
        thread_after_3 = global_ping_monitor.thread
        
        self.assertIs(thread_after_1, thread_after_2)
        self.assertIs(thread_after_2, thread_after_3)
        self.assertTrue(global_ping_monitor.running)

    def test_intermittency_alerts_endpoint(self):
        """Test GET /api/alerts/intermittency returns devices, alerts, and timestamp."""
        res = self.client.get('/api/alerts/intermittency')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertIn('devices', data)
        self.assertIn('alerts', data)
        self.assertIn('timestamp', data)

if __name__ == '__main__':
    unittest.main()
