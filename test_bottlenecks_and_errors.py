"""
Unit and integration tests for Traffic Bottlenecks and Port Errors / Buffer Drops.
Sprint: Bottlenecks & Errors Logic Enhancement
"""
import os
import sys
import unittest
import copy
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NETLENS_MASTER_KEY", "test_master_key_sprint_10_10_0_super_secure=")

from app import create_app
from app.services.config_service import ConfigService
from app.analysis.bottleneck_detector import BottleneckDetector

class TestBottlenecksConfigAdmin(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

        self._orig_config = copy.deepcopy(ConfigService.load_config())

    def tearDown(self):
        ConfigService.save_config(self._orig_config)
        ConfigService.reload_config()

    def test_get_bottlenecks_config(self):
        """Test GET /api/admin/bottlenecks-config returns default structure."""
        resp = self.client.get('/api/admin/bottlenecks-config')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        cfg = data.get('data', {})
        self.assertIn('util_warning_threshold', cfg)
        self.assertIn('util_critical_threshold', cfg)
        self.assertIn('ignore_virtual_interfaces', cfg)
        self.assertIn('error_detection_mode', cfg)
        self.assertIn('error_min_delta', cfg)
        self.assertIn('error_critical_rate', cfg)
        self.assertIn('discard_min_delta', cfg)

    def test_put_bottlenecks_config(self):
        """Test PUT /api/admin/bottlenecks-config updates thresholds."""
        new_cfg = {
            "util_warning_threshold": 80.0,
            "util_critical_threshold": 95.0,
            "ignore_virtual_interfaces": False,
            "min_speed_mbps": 50.0,
            "error_detection_mode": "rate_and_delta",
            "error_min_delta": 10,
            "error_critical_rate": 20.0,
            "discard_min_delta": 100
        }
        resp = self.client.put('/api/admin/bottlenecks-config', json=new_cfg)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        saved = data['data']
        self.assertEqual(saved['util_warning_threshold'], 80.0)
        self.assertEqual(saved['util_critical_threshold'], 95.0)
        self.assertFalse(saved['ignore_virtual_interfaces'])
        self.assertEqual(saved['error_min_delta'], 10)
        self.assertEqual(saved['discard_min_delta'], 100)

        # Confirm persistence via GET
        get_resp = self.client.get('/api/admin/bottlenecks-config')
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.get_json()['data']['util_critical_threshold'], 95.0)

    def test_bottlenecks_config_auth(self):
        """Test unauthorized and non-admin access is rejected."""
        unauth_client = self.app.test_client()
        resp = unauth_client.get('/api/admin/bottlenecks-config')
        self.assertEqual(resp.status_code, 401)

        resp_put = unauth_client.put('/api/admin/bottlenecks-config', json={})
        self.assertEqual(resp_put.status_code, 401)

        # Operator role should be forbidden to PUT
        op_client = self.app.test_client()
        with op_client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'operator'
            sess['user_role'] = 'operator'
        resp_op_put = op_client.put('/api/admin/bottlenecks-config', json={})
        self.assertEqual(resp_op_put.status_code, 403)


class TestBottlenecksAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

    def test_get_bottlenecks_legacy_format(self):
        """Test GET /api/bottlenecks returns list for backwards compatibility."""
        resp = self.client.get('/api/bottlenecks')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_get_bottlenecks_structured_format(self):
        """Test GET /api/bottlenecks?structured=true returns separated traffic and error lists."""
        resp = self.client.get('/api/bottlenecks?structured=true')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('bottlenecks', data)
        self.assertIn('errors', data)
        self.assertIn('summary', data)
        self.assertIsInstance(data['bottlenecks'], list)
        self.assertIsInstance(data['errors'], list)

        summary = data['summary']
        self.assertIn('bottlenecks_total', summary)
        self.assertIn('errors_total', summary)

    def test_get_traffic_endpoint(self):
        """Test GET /api/bottlenecks/traffic returns only high utilization items."""
        resp = self.client.get('/api/bottlenecks/traffic')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data['data'], list)
        for item in data['data']:
            self.assertEqual(item.get('type'), 'high_utilization')

    def test_get_errors_endpoint(self):
        """Test GET /api/bottlenecks/errors returns only error and discard items."""
        resp = self.client.get('/api/bottlenecks/errors')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data['data'], list)
        for item in data['data']:
            self.assertEqual(item.get('type'), 'port_errors_discards')


class TestBottleneckDetectorLogic(unittest.TestCase):
    def test_is_virtual_interface(self):
        """Test identification of virtual interfaces (loopback, SVIs, tunnels)."""
        # Virtual
        self.assertTrue(BottleneckDetector.is_virtual_interface("lo", "softwareLoopback"))
        self.assertTrue(BottleneckDetector.is_virtual_interface("Vlan 20", "l3ipvlan"))
        self.assertTrue(BottleneckDetector.is_virtual_interface("vlan100", "l2vlan"))
        self.assertTrue(BottleneckDetector.is_virtual_interface("null0", "other"))
        self.assertTrue(BottleneckDetector.is_virtual_interface("tun0", "tunnel"))
        self.assertTrue(BottleneckDetector.is_virtual_interface("veth48ab12", "ethernet"))

        # Physical
        self.assertFalse(BottleneckDetector.is_virtual_interface("GigabitEthernet1/0/1", "gigabitEthernet"))
        self.assertFalse(BottleneckDetector.is_virtual_interface("TenGigabitEthernet1/1/1", "ethernetCsmacd"))
        self.assertFalse(BottleneckDetector.is_virtual_interface("24", "ethernetCsmacd"))
        self.assertFalse(BottleneckDetector.is_virtual_interface("eth0", "ethernetCsmacd"))

    def test_traffic_utilization_logic(self):
        """Test bottleneck detector correctly computes utilization and skips virtual when requested."""
        mock_ln = MagicMock()
        mock_ln.get_devices.return_value = [
            {"device_id": 1, "hostname": "switch-core", "sysName": "SW-CORE-01"}
        ]
        # Port 1: Physical 1G with 950 Mbps (95% -> critical)
        # Port 2: Physical 1G with 760 Mbps (76% -> warning)
        # Port 3: Virtual SVI Vlan 20 with 1500 Mbps (should be ignored when ignore_virtual=True)
        # Port 4: Loopback lo with 8.5 Mbps (should be ignored)
        mock_ln.get_all_ports.return_value = [
            {
                "port_id": 101, "device_id": 1, "ifName": "TenGigabitEthernet1/1/1",
                "ifType": "ethernetCsmacd", "ifOperStatus": "up", "ifSpeed": 1000000000,
                "ifInOctets_rate": 118750000, "ifOutOctets_rate": 50000000 # 118.75 MB/s * 8 = 950 Mbps
            },
            {
                "port_id": 102, "device_id": 1, "ifName": "GigabitEthernet1/0/24",
                "ifType": "gigabitEthernet", "ifOperStatus": "up", "ifSpeed": 1000000000,
                "ifInOctets_rate": 95000000, "ifOutOctets_rate": 10000000 # 95 MB/s * 8 = 760 Mbps
            },
            {
                "port_id": 103, "device_id": 1, "ifName": "Vlan 20",
                "ifType": "l3ipvlan", "ifOperStatus": "up", "ifSpeed": 1000000000,
                "ifInOctets_rate": 187500000, "ifOutOctets_rate": 50000000 # 1.5 Gbps
            },
            {
                "port_id": 104, "device_id": 1, "ifName": "lo",
                "ifType": "softwareLoopback", "ifOperStatus": "up", "ifSpeed": 10000000,
                "ifInOctets_rate": 1062500, "ifOutOctets_rate": 1062500 # 8.5 Mbps
            }
        ]

        detector = BottleneckDetector(mock_ln)
        cfg = {
            "util_warning_threshold": 75.0,
            "util_critical_threshold": 90.0,
            "ignore_virtual_interfaces": True,
            "min_speed_mbps": 100.0
        }

        bottlenecks = detector.detect_traffic_bottlenecks(settings=cfg)
        # Should only have the 2 physical ports; Vlan 20 and lo should be excluded!
        self.assertEqual(len(bottlenecks), 2)
        self.assertEqual(bottlenecks[0]["port_name"], "TenGigabitEthernet1/1/1")
        self.assertEqual(bottlenecks[0]["severity"], "critical")
        self.assertEqual(bottlenecks[0]["util_pct"], 95.0)

        self.assertEqual(bottlenecks[1]["port_name"], "GigabitEthernet1/0/24")
        self.assertEqual(bottlenecks[1]["severity"], "warning")
        self.assertEqual(bottlenecks[1]["util_pct"], 76.0)

    def test_error_rate_and_delta_filtering(self):
        """Test that ports with old lifetime errors (delta=0, rate=0) are ignored while active ones are alerted."""
        mock_ln = MagicMock()
        mock_ln.get_devices.return_value = [
            {"device_id": 1, "hostname": "switch-access", "sysName": "SW-ACC-01"}
        ]
        # Port 1: Active physical CRC error (rate=35.0, delta=1200) -> CRITICAL
        # Port 2: Active moderate error (rate=0, delta=15) -> WARNING
        # Port 3: Old lifetime error (in_errors=1, delta=0, rate=0) -> MUST BE IGNORED!
        # Port 4: Active buffer drops (discard_delta=250) -> WARNING buffer drop
        mock_ln.get_all_ports.return_value = [
            {
                "port_id": 201, "device_id": 1, "ifName": "GigabitEthernet1/0/1",
                "ifType": "gigabitEthernet", "ifSpeed": 1000000000,
                "ifInErrors": 45000, "ifOutErrors": 0,
                "ifInErrors_rate": 35.0, "ifOutErrors_rate": 0,
                "ifInErrors_delta": 1200, "ifOutErrors_delta": 0,
                "ifInDiscards": 0, "ifOutDiscards": 0,
                "ifInDiscards_rate": 0, "ifInDiscards_delta": 0
            },
            {
                "port_id": 202, "device_id": 1, "ifName": "GigabitEthernet1/0/2",
                "ifType": "gigabitEthernet", "ifSpeed": 1000000000,
                "ifInErrors": 50, "ifOutErrors": 0,
                "ifInErrors_rate": 0, "ifOutErrors_rate": 0,
                "ifInErrors_delta": 15, "ifOutErrors_delta": 0,
                "ifInDiscards": 0, "ifOutDiscards": 0,
                "ifInDiscards_rate": 0, "ifInDiscards_delta": 0
            },
            {
                "port_id": 203, "device_id": 1, "ifName": "GigabitEthernet1/0/40",
                "ifType": "gigabitEthernet", "ifSpeed": 1000000000,
                "ifInErrors": 1, "ifOutErrors": 0, # Old 1-packet error from months ago
                "ifInErrors_rate": 0, "ifOutErrors_rate": 0,
                "ifInErrors_delta": 0, "ifOutErrors_delta": 0,
                "ifInDiscards": 0, "ifOutDiscards": 0,
                "ifInDiscards_rate": 0, "ifInDiscards_delta": 0
            },
            {
                "port_id": 204, "device_id": 1, "ifName": "GigabitEthernet1/0/48",
                "ifType": "gigabitEthernet", "ifSpeed": 1000000000,
                "ifInErrors": 0, "ifOutErrors": 0,
                "ifInErrors_rate": 0, "ifOutErrors_rate": 0,
                "ifInErrors_delta": 0, "ifOutErrors_delta": 0,
                "ifInDiscards": 500, "ifOutDiscards": 0,
                "ifInDiscards_rate": 5.0, "ifOutDiscards_delta": 250
            }
        ]

        detector = BottleneckDetector(mock_ln)
        cfg = {
            "error_detection_mode": "rate_and_delta",
            "error_min_delta": 5,
            "error_critical_rate": 10.0,
            "discard_min_delta": 50
        }

        errors = detector.detect_port_errors(settings=cfg)
        # Port 203 (1 error lifetime, 0 delta) MUST NOT BE IN ERRORS LIST!
        port_ids = [e["port_id"] for e in errors]
        self.assertNotIn(2013, port_ids)
        self.assertNotIn(203, port_ids)

        # Port 201 (active high rate) -> critical CRC
        p201 = next(e for e in errors if e["port_id"] == 201)
        self.assertEqual(p201["severity"], "critical")
        self.assertEqual(p201["category"], "crc_physical")

        # Port 202 (active delta) -> warning CRC
        p202 = next(e for e in errors if e["port_id"] == 202)
        self.assertEqual(p202["severity"], "warning")
        self.assertEqual(p202["category"], "crc_physical")

        # Port 204 (buffer drop) -> buffer drop
        p204 = next(e for e in errors if e["port_id"] == 204)
        self.assertEqual(p204["category"], "buffer_drop")


class TestConnectedDeviceAndLiveSNMP(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

    def test_connected_device_in_mock_traffic(self):
        """Test that traffic bottlenecks include connected_device and is_switch."""
        resp = self.client.get('/api/bottlenecks/traffic')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        for item in data['data']:
            self.assertIn('connected_device', item)
            self.assertIn('is_switch', item)
            conn = item['connected_device']
            self.assertIn('type', conn)
            self.assertIn('label', conn)

    def test_live_snmp_mock(self):
        """Test GET /api/bottlenecks/live-snmp returns instantaneous rate."""
        resp = self.client.get('/api/bottlenecks/live-snmp?device_ip=172.16.11.1&if_index=36&community=RTVZABBIX')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('in_rate_mbps', data)
        self.assertIn('out_rate_mbps', data)

    def test_live_snmp_missing_params(self):
        """Test GET /api/bottlenecks/live-snmp requires device_ip and if_index."""
        resp = self.client.get('/api/bottlenecks/live-snmp')
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()

