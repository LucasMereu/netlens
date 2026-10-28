"""
Unit and integration tests for Traffic History, Real-time SNMP/Zabbix Meter, and Device Interface Search.
Sprint: Real-time Traffic Graphs & Host Search
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NETLENS_MASTER_KEY", "test_master_key_sprint_10_10_0_super_secure=")

from app import create_app


class TestTrafficAndHostSearchAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

    # --- 1. /api/bottlenecks/live-snmp ---

    def test_live_snmp_auth(self):
        """Test /api/bottlenecks/live-snmp requires authentication."""
        unauth = self.app.test_client()
        resp = unauth.get('/api/bottlenecks/live-snmp?device_ip=10.0.0.1&if_index=1')
        self.assertEqual(resp.status_code, 401)

    def test_live_snmp_missing_params(self):
        """Test /api/bottlenecks/live-snmp requires device_ip."""
        resp = self.client.get('/api/bottlenecks/live-snmp')
        self.assertEqual(resp.status_code, 400)

    def test_live_snmp_fallback_response(self):
        """Test /api/bottlenecks/live-snmp returns valid rate structure even under network isolation."""
        resp = self.client.get('/api/bottlenecks/live-snmp?device_ip=192.168.4.195&if_index=9&interface=lagg1')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('in_rate_mbps', data)
        self.assertIn('out_rate_mbps', data)
        self.assertIn('source', data)
        self.assertEqual(data.get('device_ip'), '192.168.4.195')

    def test_live_snmp_with_zabbix_fallback_mock(self):
        """Test /api/bottlenecks/live-snmp successfully uses Zabbix fallback when SNMP fails."""
        mock_zb = MagicMock()
        mock_zb._request_api.side_effect = lambda method, params: (
            [{"hostid": "11198", "host": "SRVTRUENAS02-BKP", "name": "192.168.4.195 - SRVTRUENAS02-BKP"}] if method == "host.get"
            else [
                {"itemid": "107423", "name": "Interface [lagg1()]: Bits received", "key_": "net.if.in[9]", "lastvalue": "1959863056", "lastclock": 1773600000},
                {"itemid": "107441", "name": "Interface [lagg1()]: Bits sent", "key_": "net.if.out[9]", "lastvalue": "1323598408", "lastclock": 1773600000}
            ] if method == "item.get"
            else None
        )

        with patch('app.routes.bottlenecks.get_zabbix_client', return_value=mock_zb):
            with patch('subprocess.run', side_effect=Exception("SNMP timeout")):
                resp = self.client.get('/api/bottlenecks/live-snmp?device_ip=192.168.4.195&if_index=9&interface=lagg1')
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data.get('success'))
                self.assertEqual(data.get('source'), 'zabbix_live')
                self.assertAlmostEqual(data.get('in_rate_mbps'), 1959.86, places=1)
                self.assertAlmostEqual(data.get('out_rate_mbps'), 1323.60, places=1)

    # --- 2. /api/traffic/history ---

    def test_traffic_history_auth(self):
        """Test /api/traffic/history requires authentication."""
        unauth = self.app.test_client()
        resp = unauth.get('/api/traffic/history?device_ip=10.0.0.1&interface=eth0')
        self.assertEqual(resp.status_code, 401)

    def test_traffic_history_missing_device(self):
        """Test /api/traffic/history requires device_ip."""
        resp = self.client.get('/api/traffic/history')
        self.assertEqual(resp.status_code, 400)

    def test_traffic_history_mock_response(self):
        """Test /api/traffic/history returns time series data and statistics."""
        with patch('app.routes.bottlenecks.is_mock_mode', return_value=True):
            resp = self.client.get('/api/traffic/history?device_ip=192.168.4.195&interface=lagg1&hours=1')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get('success'))
            self.assertIn('timestamps', data)
            self.assertIn('in_mbps', data)
            self.assertIn('out_mbps', data)
            self.assertIn('stats', data)
            self.assertEqual(len(data['timestamps']), len(data['in_mbps']))
            self.assertEqual(len(data['timestamps']), len(data['out_mbps']))

            stats = data['stats']
            self.assertIn('cur_in_mbps', stats)
            self.assertIn('max_in_mbps', stats)
            self.assertIn('avg_in_mbps', stats)
            self.assertIn('cur_out_mbps', stats)
            self.assertIn('max_out_mbps', stats)
            self.assertIn('avg_out_mbps', stats)
            self.assertGreater(stats['max_in_mbps'], 0)

    def test_traffic_history_zabbix_real_mock(self):
        """Test /api/traffic/history parses Zabbix history.get correctly into Mbps series."""
        mock_zb = MagicMock()
        mock_zb._request_api.side_effect = lambda method, params: (
            [{"hostid": "11198", "host": "SRVTRUENAS02-BKP", "name": "SRVTRUENAS02-BKP"}] if method == "host.get"
            else [
                {"itemid": "101", "name": "Interface [lagg1()]: Bits received", "key_": "net.if.in[9]", "lastvalue": "1900000000"},
                {"itemid": "102", "name": "Interface [lagg1()]: Bits sent", "key_": "net.if.out[9]", "lastvalue": "1300000000"}
            ] if method == "item.get"
            else [
                {"clock": "1773600000", "value": "1900000000"},
                {"clock": "1773600060", "value": "2100000000"},
                {"clock": "1773600120", "value": "1950000000"}
            ] if method == "history.get" and params.get("itemids") == ["101"]
            else [
                {"clock": "1773600000", "value": "1300000000"},
                {"clock": "1773600060", "value": "1400000000"},
                {"clock": "1773600120", "value": "1350000000"}
            ] if method == "history.get" and params.get("itemids") == ["102"]
            else None
        )

        with patch('app.routes.bottlenecks.is_mock_mode', return_value=False):
            with patch('app.routes.bottlenecks.get_zabbix_client', return_value=mock_zb):
                resp = self.client.get('/api/traffic/history?device_ip=192.168.4.195&interface=lagg1&hours=1')
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data.get('success'))
                self.assertEqual(len(data['timestamps']), 3)
                self.assertEqual(data['in_mbps'], [1900.0, 2100.0, 1950.0])
                self.assertEqual(data['out_mbps'], [1300.0, 1400.0, 1350.0])
                self.assertEqual(data['stats']['max_in_mbps'], 2100.0)
                self.assertEqual(data['stats']['max_out_mbps'], 1400.0)

    # --- 3. /api/devices/search-interfaces ---

    def test_search_interfaces_auth(self):
        """Test /api/devices/search-interfaces requires authentication."""
        unauth = self.app.test_client()
        resp = unauth.get('/api/devices/search-interfaces?query=10.0.0.1')
        self.assertEqual(resp.status_code, 401)

    def test_search_interfaces_missing_query(self):
        """Test /api/devices/search-interfaces requires query parameter."""
        resp = self.client.get('/api/devices/search-interfaces')
        self.assertEqual(resp.status_code, 400)

    def test_search_interfaces_mock(self):
        """Test /api/devices/search-interfaces returns device info and interfaces in mock mode."""
        with patch('app.routes.bottlenecks.is_mock_mode', return_value=True):
            resp = self.client.get('/api/devices/search-interfaces?query=192.168.4.195')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get('success'))
            self.assertIn('device', data)
            self.assertIn('interfaces', data)
            self.assertEqual(data['device']['name'], 'SRVTRUENAS02-BKP')
            self.assertGreater(len(data['interfaces']), 0)
            lagg1 = next((i for i in data['interfaces'] if i['name'] == 'lagg1'), None)
            self.assertIsNotNone(lagg1)
            self.assertEqual(lagg1['oper_status'], 'up')
            self.assertEqual(lagg1['speed_mbps'], 20000.0)

    def test_search_interfaces_librenms_mock(self):
        """Test /api/devices/search-interfaces resolves ports from LibreNMS correctly."""
        mock_ln = MagicMock()
        mock_ln.get_devices.return_value = [
            {"device_id": 195, "hostname": "192.168.4.195", "sysName": "SRVTRUENAS02-BKP", "os": "freebsd", "hardware": "Supermicro", "community": "RTVZABBIX"}
        ]
        mock_ln.get_device_ports.return_value = [
            {
                "port_id": 901, "ifIndex": 9, "ifName": "lagg1", "ifAlias": "LACP Trunk",
                "ifOperStatus": "up", "ifType": "ieee8023adLag", "ifSpeed": 20000000000,
                "ifInOctets_rate": 244982882, "ifOutOctets_rate": 165449801 # ~1960 Mbps In, ~1323 Mbps Out
            },
            {
                "port_id": 902, "ifIndex": 1, "ifName": "ix0", "ifAlias": "Physical SFP+",
                "ifOperStatus": "up", "ifType": "ethernetCsmacd", "ifSpeed": 10000000000,
                "ifInOctets_rate": 122491441, "ifOutOctets_rate": 82724900
            }
        ]

        with patch('app.routes.bottlenecks.is_mock_mode', return_value=False):
            with patch('app.routes.bottlenecks.get_librenms_client', return_value=mock_ln):
                with patch('app.routes.bottlenecks.get_zabbix_client', return_value=None):
                    resp = self.client.get('/api/devices/search-interfaces?query=192.168.4.195')
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertTrue(data.get('success'))
                    self.assertEqual(data['device']['name'], 'SRVTRUENAS02-BKP')
                    self.assertEqual(data['device']['type'], 'Servidor / Storage')
                    self.assertEqual(len(data['interfaces']), 2)
                    self.assertAlmostEqual(data['interfaces'][0]['in_rate_mbps'], 1959.86, places=1)


if __name__ == '__main__':
    unittest.main()
