"""
Unit and integration tests for Port Events Flapping and STP / BPDU Protect detection.
Sprint: Port Events Enhancement
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
from app.analysis.port_event_tracker import PortEventTracker

class TestPortEventsConfigAdmin(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

        self._orig_config = copy.deepcopy(ConfigService.load_config())

    def tearDown(self):
        ConfigService.save_config(self._orig_config)
        ConfigService.reload_config()

    def test_get_port_events_config(self):
        """Test GET /api/admin/port-events-config returns correct structure and defaults."""
        resp = self.client.get('/api/admin/port-events-config')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        settings = data.get('data', {})
        self.assertIn('flapping_warning_threshold', settings)
        self.assertIn('flapping_critical_threshold', settings)
        self.assertIn('default_window_hours', settings)
        self.assertIn('stp_patterns', settings)
        self.assertIsInstance(settings['stp_patterns'], list)
        self.assertGreaterEqual(len(settings['stp_patterns']), 1)

    def test_put_port_events_config(self):
        """Test PUT /api/admin/port-events-config updates configuration successfully."""
        new_cfg = {
            "flapping_warning_threshold": 5,
            "flapping_critical_threshold": 10,
            "default_window_hours": 12,
            "stp_patterns": [
                "port % is Blocked by STP",
                "BPDU Guard triggered on port %",
                "Custom STP rule %"
            ]
        }
        resp = self.client.put('/api/admin/port-events-config', json=new_cfg)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data['data']['flapping_warning_threshold'], 5)
        self.assertEqual(data['data']['flapping_critical_threshold'], 10)
        self.assertEqual(data['data']['default_window_hours'], 12)
        self.assertEqual(len(data['data']['stp_patterns']), 3)

        # Verify persistence via GET
        get_resp = self.client.get('/api/admin/port-events-config')
        self.assertEqual(get_resp.status_code, 200)
        saved = get_resp.get_json()['data']
        self.assertEqual(saved['flapping_warning_threshold'], 5)
        self.assertEqual(saved['flapping_critical_threshold'], 10)
        self.assertEqual(saved['default_window_hours'], 12)

    def test_put_port_events_config_validation(self):
        """Test PUT /api/admin/port-events-config handles edge cases safely."""
        bad_cfg = {
            "flapping_warning_threshold": -1,  # below min 1 -> clamps to 1
            "flapping_critical_threshold": 500, # above max 200 -> clamps to 200
            "default_window_hours": "invalid", # invalid str -> ignored/keeps current
            "stp_patterns": "not_a_list"       # invalid -> ignored
        }
        resp = self.client.put('/api/admin/port-events-config', json=bad_cfg)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        # Should enforce bounds
        self.assertEqual(data['flapping_warning_threshold'], 1)
        self.assertEqual(data['flapping_critical_threshold'], 200)

    def test_unauthorized_access(self):
        """Test endpoints reject unauthenticated or non-admin users."""
        unauth_client = self.app.test_client()
        resp = unauth_client.get('/api/admin/port-events-config')
        self.assertEqual(resp.status_code, 401)

        resp_put = unauth_client.put('/api/admin/port-events-config', json={})
        self.assertEqual(resp_put.status_code, 401)


class TestPortEventsAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

    def test_get_port_events_paginated_structure(self):
        """Test GET /api/ports/events?paginate=true returns events and summary structures."""
        resp = self.client.get('/api/ports/events?paginate=true&hours=24')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('events', data)
        self.assertIn('summary', data)
        self.assertIsInstance(data['events'], list)
        
        summary = data['summary']
        self.assertIn('total', summary)
        self.assertIn('stp_blocked', summary)
        self.assertIn('flapping', summary)
        self.assertIn('hours', summary)

    def test_get_port_events_flat_structure(self):
        """Test GET /api/ports/events returns array for backwards compatibility."""
        resp = self.client.get('/api/ports/events?hours=24&limit=10')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        if len(data) > 0:
            first = data[0]
            self.assertIn('port_id', first)
            self.assertIn('flaps', first)
            self.assertIn('stp_blocked', first)

    def test_get_port_events_filtering(self):
        """Test query params hours, min_flaps, and stp_only."""
        # Test STP only filter
        resp_stp = self.client.get('/api/ports/events?paginate=true&stp_only=true')
        self.assertEqual(resp_stp.status_code, 200)
        stp_data = resp_stp.get_json()
        self.assertIn('events', stp_data)
        for item in stp_data['events']:
            self.assertTrue(item.get('stp_blocked'))

        # Test min_flaps filter
        resp_flaps = self.client.get('/api/ports/events?paginate=true&min_flaps=5')
        self.assertEqual(resp_flaps.status_code, 200)
        flaps_data = resp_flaps.get_json()
        self.assertIn('events', flaps_data)
        for item in flaps_data['events']:
            self.assertGreaterEqual(item.get('flaps', 0), 5)


class TestPortEventTrackerLogic(unittest.TestCase):
    def test_flapping_classification(self):
        """Test flapping level classification based on thresholds."""
        # Flaps below warning
        self.assertEqual(PortEventTracker.classify_flapping(0, 3, 6), 'none')
        self.assertEqual(PortEventTracker.classify_flapping(2, 3, 6), 'none')
        # Flaps in warning range
        self.assertEqual(PortEventTracker.classify_flapping(3, 3, 6), 'warning')
        self.assertEqual(PortEventTracker.classify_flapping(5, 3, 6), 'warning')
        # Flaps in critical range
        self.assertEqual(PortEventTracker.classify_flapping(6, 3, 6), 'critical')
        self.assertEqual(PortEventTracker.classify_flapping(20, 3, 6), 'critical')

    def test_tracker_db_query_and_aggregation(self):
        """Test that tracker properly queries eventlog, syslog, and ports_stp and merges them."""
        mock_librenms = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_librenms.get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock eventlog flap query (pid 5307 has 7 flaps)
        mock_eventlog_rows = [
            (5307, 7, "2026-09-14 16:49:05"),
            (2001, 2, "2026-09-14 10:00:00")
        ]
        # Mock ports_stp query (SELECT port_id, state)
        mock_ports_stp_rows = [
            (5307, "blocking")
        ]
        # Mock syslog STP query (SELECT s.device_id, s.timestamp, s.msg, s.program)
        mock_syslog_rows = [
            (190, "2026-09-14 17:01:03", "port 12 is Blocked by STP [00435]", "STP")
        ]

        # Cursor executes 3 queries in _fetch_flaps_and_stp:
        # 1) eventlog, 2) ports_stp, 3) syslog
        mock_cursor.fetchall.side_effect = [
            mock_eventlog_rows,
            mock_ports_stp_rows,
            mock_syslog_rows
        ]

        tracker = PortEventTracker(mock_librenms)
        cfg = {
            "flapping_warning_threshold": 3,
            "flapping_critical_threshold": 6,
            "default_window_hours": 24,
            "stp_patterns": ["Blocked by STP"]
        }

        flaps_by_pid, flaps_by_dev_port, stp_by_dev_port, stp_blocked_pids = tracker._fetch_flaps_and_stp(24, cfg)

        self.assertIn("5307", flaps_by_pid)
        self.assertEqual(flaps_by_pid["5307"], 7)
        self.assertIn("2001", flaps_by_pid)
        self.assertEqual(flaps_by_pid["2001"], 2)

        self.assertIn(5307, stp_blocked_pids)
        # Port 12 on device 190 in syslog
        self.assertIn((190, "12"), stp_by_dev_port)
        self.assertEqual(stp_by_dev_port[(190, "12")]["type"], "BPDU Protect / STP Block")
        self.assertIn("Blocked by STP", stp_by_dev_port[(190, "12")]["message"])


if __name__ == '__main__':
    unittest.main()
