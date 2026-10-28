import os
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from app.analysis.ping_monitor import PingMonitor
from app.services.config_service import ConfigService
from app.services.provision_orchestrator import ProvisionOrchestrator

class TestSprint10121Remediation(unittest.TestCase):
    """
    Validation test suite for Sprint 10.12.1 Phase B Surgical Remediation:
    - F-01: PingMonitor handles empty targets gracefully without ThreadPoolExecutor ValueError.
    - F-02: PingMonitor exposes both canonical metrics and compatibility aliases.
    - F-02 (UI): templates/index.html safely extracts metrics preventing undefined% Perda.
    - F-03/F-04: Strict HTTP 202 contract enforcement on /api/v1/provision/apply.
    """

    @classmethod
    def setUpClass(cls):
        os.environ["NETLENS_MASTER_KEY"] = "test_master_key_sprint_10_10_0_super_secure="

    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def test_1_ping_monitor_empty_targets_no_crash(self):
        """F-01: Verify PingMonitor initializes without crashing when targets is empty in real mode."""
        try:
            pm = PingMonitor(targets={}, simulation_mode=False)
            self.assertEqual(len(pm.targets), 0)
            self.assertEqual(len(pm.groups), 0)
            self.assertEqual(pm.alerts, [])
            latest = pm.get_latest_data()
            self.assertEqual(latest["devices"], {})
            self.assertEqual(latest["alerts"], [])
        except ValueError as ve:
            self.fail(f"PingMonitor raised ValueError on empty targets: {ve}")

    def test_2_ping_monitor_metrics_contract(self):
        """F-02: Verify PingMonitor intermittency alert contains canonical metrics and compatibility aliases."""
        sample_targets = {
            "10.11.0.249": {"name": "Dell Mgmt", "group": "control_plane"},
            "10.1.1.1": {"name": "Dell PtP", "group": "control_plane"},
            "10.1.1.2": {"name": "Sophos FW", "group": "data_plane"},
            "10.11.0.248": {"name": "Dell Eth", "group": "data_plane"}
        }
        pm = PingMonitor(targets=sample_targets, simulation_mode=True)
        pm.sim_tick = 8
        pm._ping_all()

        self.assertTrue(len(pm.alerts) > 0, "Expected an intermittency alert during tick 8")
        alert = pm.alerts[0]
        metrics = alert["metrics"]

        # Canonical generic keys
        self.assertIn("avg_control_plane_loss", metrics)
        self.assertIn("avg_data_plane_loss", metrics)
        self.assertIn("individual_losses", metrics)
        self.assertIsInstance(metrics["individual_losses"], dict)

        # Compatibility aliases for legacy frontend
        self.assertIn("dell_mgmt_loss", metrics)
        self.assertIn("dell_ptp_loss", metrics)
        self.assertIn("sophos_loss", metrics)
        self.assertIn("dell_eth_loss", metrics)

        # Values should be numbers, not None
        self.assertIsInstance(metrics["dell_mgmt_loss"], (int, float))
        self.assertIsInstance(metrics["dell_ptp_loss"], (int, float))
        self.assertIsInstance(metrics["sophos_loss"], (int, float))
        self.assertIsInstance(metrics["dell_eth_loss"], (int, float))

    def test_3_frontend_template_metrics_resilience(self):
        """F-02 (UI): Verify templates/index.html safely extracts metrics avoiding undefined% Perda."""
        template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("dell_mgmt_loss ??", content)
        self.assertIn("dell_ptp_loss ??", content)
        self.assertIn("sophos_loss ??", content)
        self.assertIn("dell_eth_loss ??", content)
        self.assertIn("individual_losses", content)

    def test_4_strict_apply_202_contract(self):
        """F-03/F-04: Verify POST /api/v1/provision/apply returns strictly HTTP 202 and QUEUED status."""
        config = ConfigService.load_config()
        input_data = {
            "hostname": "sw-rem-test-01",
            "ip": "10.11.4.222",
            "site": "RedeTV HQ",
            "model": "Generic Switch",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "NetLens-REM-Secure-10f0a91"
        }
        with patch("requests.get") as p_get, patch("requests.post") as p_post, patch("requests.patch") as p_patch:
            p_get.return_value = MagicMock(status_code=200, json=lambda: {"results": [], "count": 0})
            p_post.return_value = MagicMock(status_code=200, json=lambda: {"result": "mock_token", "id": 1})
            p_patch.return_value = MagicMock(status_code=200, json=lambda: {"result": "ok"})

            plan = ProvisionOrchestrator.generate_plan(input_data, config)
            plan_id = plan["plan_id"]
            plan_hash = plan["hash"]
            ProvisionOrchestrator.approve_plan(plan_id, plan_hash)

            res = self.client.post('/api/v1/provision/apply', json={"plan_id": plan_id, "hash": plan_hash})
            self.assertEqual(res.status_code, 202)
            data = res.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "QUEUED")
            self.assertTrue(data["async"])
            self.assertIn("job_id", data)

if __name__ == '__main__':
    unittest.main()
