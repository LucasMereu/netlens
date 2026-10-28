import unittest
from unittest.mock import patch, MagicMock

from app.models.provision_policy import PolicyValidationResult
from app.policies.provision_policy_engine import ProvisionPolicyEngine
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE

class TestProvisionPolicyEngine(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }

    def test_naming_policy_prefix_warning(self):
        # Hostname without 'sw-' prefix for NETWORK_SWITCH profile should generate warning but pass
        input_data = {
            "hostname": "core-switch-01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "snmp_community": "rtvzabbix"
        }
        res = ProvisionPolicyEngine.evaluate_policies(input_data, "NETWORK_SWITCH")
        self.assertTrue(res.passed)
        self.assertTrue(any(w.rule == "RECOMMENDED_HOSTNAME_PREFIX" for w in res.warnings))

    def test_naming_policy_invalid_characters_violation(self):
        # Hostname with invalid special characters (e.g. spaces/slashes) must fail
        input_data = {
            "hostname": "sw-core / 01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "snmp_community": "rtvzabbix"
        }
        res = ProvisionPolicyEngine.evaluate_policies(input_data, "NETWORK_SWITCH")
        self.assertFalse(res.passed)
        self.assertTrue(any(v.rule == "INVALID_HOSTNAME_CHARACTERS" for v in res.violations))

    def test_security_policy_weak_snmp_community_warning(self):
        # 'public' community should generate weak community warning
        input_data = {
            "hostname": "sw-access-01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "snmp_community": "public"
        }
        res = ProvisionPolicyEngine.evaluate_policies(input_data, "NETWORK_SWITCH")
        self.assertTrue(res.passed)
        self.assertTrue(any(w.rule == "WEAK_SNMP_COMMUNITY" for w in res.warnings))

    def test_inventory_policy_mandatory_site(self):
        # Missing site should trigger CRITICAL inventory violation
        input_data = {
            "hostname": "sw-access-01",
            "ip": "10.11.0.250",
            "site": "",
            "snmp_community": "rtvzabbix"
        }
        res = ProvisionPolicyEngine.evaluate_policies(input_data, "NETWORK_SWITCH")
        self.assertFalse(res.passed)
        self.assertTrue(any(v.rule == "MANDATORY_SITE" for v in res.violations))

    def test_ownership_tags_generation(self):
        input_data = {
            "hostname": "sw-access-01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "snmp_community": "rtvzabbix"
        }
        res = ProvisionPolicyEngine.evaluate_policies(input_data, "NETWORK_SWITCH")
        self.assertEqual(res.tags["ManagedBy"], "NetLens")
        self.assertEqual(res.tags["Profile"], "NETWORK_SWITCH")

    @patch("requests.get")
    def test_policy_violation_halts_orchestrator_plan_generation(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"results": []}
        mock_get.return_value = mock_res

        # Invalid hostname must halt plan generation with POLICY_VIOLATION error
        invalid_input = {
            "hostname": "sw-invalid * name",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH"
        }
        with self.assertRaises(ValueError) as ctx:
            ProvisionOrchestrator.generate_plan(invalid_input, self.mock_config)
        self.assertIn("POLICY_VIOLATION", str(ctx.exception))

if __name__ == '__main__':
    unittest.main()
