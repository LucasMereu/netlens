# Unit tests for Server & Network Inventory Service & Routes
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.server_inventory_service import ServerInventoryService

class TestServerInventory(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SECRET_KEY'] = 'test_secret'
        self.client = self.app.test_client()

    def test_byte_and_uptime_formatters(self):
        self.assertEqual(ServerInventoryService._format_bytes(1024), '1.0 KB')
        self.assertEqual(ServerInventoryService._format_bytes(1048576), '1.0 MB')
        self.assertEqual(ServerInventoryService._format_bytes(1073741824), '1.0 GB')
        self.assertEqual(ServerInventoryService._format_uptime(3665), '1h 1m')
        self.assertEqual(ServerInventoryService._format_uptime(90000), '1d 1h 0m')

    def test_unauthorized_access(self):
        res = self.client.get('/api/inventory/servers')
        self.assertEqual(res.status_code, 401)
        res_cat = self.client.get('/api/inventory/devices/switches')
        self.assertEqual(res_cat.status_code, 401)
        res_csv = self.client.get('/api/reports/devices/switches/csv')
        self.assertEqual(res_csv.status_code, 401)

    @patch('app.services.server_inventory_service.get_zabbix_client')
    @patch('app.services.server_inventory_service.get_librenms_client')
    def test_inventory_endpoint_authorized(self, mock_lnms, mock_zb):
        mock_zb.return_value = None
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_lnms.return_value = mock_client
        mock_client.get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock devices
        mock_cursor.fetchall.side_effect = [
            # devices
            [{
                'device_id': 101, 'hostname': 'srv-app01', 'sysName': 'srv-app01',
                'ip': '10.11.1.50', 'os': 'linux', 'version': 'Ubuntu 22.04',
                'hardware': 'Dell PowerEdge', 'status': 1, 'status_reason': '',
                'uptime': 86400, 'purpose': 'App Server'
            }],
            # processors
            [{'device_id': 101, 'processor_descr': 'Intel Xeon Gold 6248R', 'processor_usage': 25.5}],
            # mempools
            [{'device_id': 101, 'mempool_descr': 'Physical memory', 'mempool_perc': 40.0, 'mempool_total': 34359738368, 'mempool_used': 13743895347, 'mempool_free': 20615843021}],
            # storage
            [{'device_id': 101, 'storage_descr': '/', 'storage_size': 107374182400, 'storage_used': 42949672960, 'storage_free': 64424509440, 'storage_perc': 40.0}]
        ]

        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

        res = self.client.get('/api/inventory/servers?force=true')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['summary']['total_servers'], 1)
        self.assertEqual(data['summary']['online_servers'], 1)
        self.assertEqual(len(data['servers']), 1)
        srv = data['servers'][0]
        self.assertEqual(srv['hostname'], 'srv-app01')
        self.assertEqual(srv['cpu']['model'], 'Intel Xeon Gold 6248R')
        self.assertEqual(srv['cpu']['percent'], 25.5)
        self.assertEqual(srv['memory']['total_formatted'], '32.0 GB')
        self.assertEqual(srv['storage']['partitions'][0]['mount'], '/')

    @patch('app.services.server_inventory_service.get_librenms_client')
    def test_category_inventory_and_csv_reports(self, mock_lnms):
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_lnms.return_value = mock_client
        mock_client.get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock devices for category switches
        mock_cursor.fetchall.side_effect = [
            # rows
            [
                {
                    'device_id': 201, 'hostname': 'sw-core-01', 'sysName': 'sw-core-01',
                    'ip': '10.11.0.1', 'hardware': 'Dell S4048-ON', 'os': 'ftos',
                    'version': '9.14', 'status': 1, 'status_reason': '',
                    'last_ping_timetaken': 0.005, 'uptime': 500000
                },
                {
                    'device_id': 202, 'hostname': 'sw-dist-hpe', 'sysName': 'sw-dist-hpe',
                    'ip': '10.11.0.2', 'hardware': 'HPE 1930 JL685A', 'os': 'procurve',
                    'version': '1.0', 'status': 1, 'status_reason': '',
                    'last_ping_timetaken': 0.010, 'uptime': 200000
                }
            ],
            # ports
            [
                {'device_id': 201, 'total_ports': 48, 'active_ports': 24},
                {'device_id': 202, 'total_ports': 24, 'active_ports': 12}
            ]
        ]

        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

        # Test API endpoint
        res = self.client.get('/api/inventory/devices/switches?force=true')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['summary']['total'], 2)
        self.assertEqual(data['summary']['online'], 2)
        self.assertIn('Dell', data['summary']['vendor_counts'])
        self.assertIn('HPE / Aruba', data['summary']['vendor_counts'])

        # Test CSV Report endpoint
        csv_res = self.client.get('/api/reports/devices/switches/csv')
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn('text/csv', csv_res.headers.get('Content-Type'))
        csv_text = csv_res.data.decode('utf-8')
        self.assertIn('sw-core-01', csv_text)
        self.assertIn('sw-dist-hpe', csv_text)
        self.assertIn('Dell S4048-ON', csv_text)

if __name__ == '__main__':
    unittest.main()
