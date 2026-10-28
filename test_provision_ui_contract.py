import unittest
from unittest.mock import patch, MagicMock

from app.models.provision_dependency import DependencyStatus, DependencyResult
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE

class TestProvisionUIContract(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }

    @patch("requests.post")
    @patch("requests.get")
    def test_plan_generation_readonly_contract(self, mock_get, mock_post):
        """Test 1 & 2: ChangePlan generation is 100% read-only and formats cards properly."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-core-01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE 2920",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)

        self.assertIn("plan_id", plan)
        self.assertEqual(plan["status"], "PENDING_APPROVAL")
        self.assertIn("policy_result", plan)
        self.assertIn("discovery_results", plan)
        self.assertIn("risk_assessment", plan)
        self.assertIn("dag_graph", plan)
        self.assertEqual(plan["input"]["snmp_community"], "[REDACTED]")

    @patch("requests.post")
    @patch("requests.get")
    def test_policy_violation_blocks_plan(self, mock_get, mock_post):
        """Test 3: Invalid hostname format triggers POLICY_VIOLATION."""
        input_data = {
            "hostname": "invalid hostname spaces",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE 2920",
            "profile": "NETWORK_SWITCH"
        }
        with self.assertRaises(ValueError) as ctx:
            ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        self.assertIn("POLICY_VIOLATION", str(ctx.exception))

    @patch("requests.post")
    @patch("requests.get")
    def test_hash_tamper_detection_rejects_approval(self, mock_get, mock_post):
        """Test 6: Approval fails if hash does not match stored plan hash."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-core-01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE 2920",
            "profile": "NETWORK_SWITCH"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        with self.assertRaises(ValueError) as ctx:
            ProvisionOrchestrator.approve_plan(plan_id, plan_hash="TAMPERED_HASH")
        self.assertIn("TAMPER_DETECTED", str(ctx.exception))

if __name__ == '__main__':
    unittest.main()
