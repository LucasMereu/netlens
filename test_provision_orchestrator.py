import unittest
from unittest.mock import patch, MagicMock
import json
import os

from app.models.provision_profile import BUILTIN_PROFILES, ProvisionProfile
from app.services.provision_capability_engine import ProvisionCapabilityEngine
from app.services.provision_profile_engine import ProvisionProfileEngine
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE
from app.services.provision_reconciliation import ProvisionReconciliationEngine

class TestProvisionOrchestrator(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }

    def test_builtin_profiles_exist(self):
        self.assertIn("NETWORK_SWITCH", BUILTIN_PROFILES)
        self.assertIn("ROUTER_CISCO", BUILTIN_PROFILES)
        self.assertIn("FIREWALL_SOPHOS", BUILTIN_PROFILES)
        self.assertIn("SERVER_LINUX", BUILTIN_PROFILES)
        self.assertIn("VM_PROXMOX", BUILTIN_PROFILES)

    def test_capability_resolution(self):
        # HPE 1930 should be Web Managed / Instant On (no full CLI / VLAN API capability)
        hpe_caps = ProvisionCapabilityEngine.get_capabilities("HPE OfficeConnect 1930 JL685A", "HPE", "NETWORK_SWITCH")
        self.assertFalse(hpe_caps["ssh"])
        self.assertFalse(hpe_caps["cli_configuration"])
        self.assertTrue(hpe_caps["web_only"])

        # 3Com 2928 should have SSH CLI capability
        com_caps = ProvisionCapabilityEngine.get_capabilities("3Com 2928", "3Com", "NETWORK_SWITCH")
        self.assertTrue(com_caps["ssh"])
        self.assertTrue(com_caps["cli_configuration"])

    @patch("requests.post")
    @patch("requests.get")
    def test_generate_plan_deterministic_hash_and_secret_redaction(self, mock_get, mock_post):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"results": []}
        mock_get.return_value = mock_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-lab01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE OfficeConnect 1930 JL685A",
            "profile": "NETWORK_SWITCH",
            "snmp_version": "v2c",
            "snmp_community": "SUPER_SECRET_COMMUNITY_123"
        }

        plan1 = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        self.assertIn("PROV-2026-", plan1["plan_id"])
        self.assertEqual(plan1["input"]["snmp_community"], "[REDACTED]") # Secret Redacted
        self.assertNotIn("SUPER_SECRET_COMMUNITY_123", json.dumps(plan1))

        # Test deterministic hash for identical input
        plan2 = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        self.assertEqual(plan1["hash"], plan2["hash"])

    @patch("requests.post")
    @patch("requests.get")
    def test_unapproved_plan_cannot_be_applied(self, mock_get, mock_post):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"results": []}
        mock_get.return_value = mock_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-test-unapproved",
            "ip": "10.11.0.251",
            "site": "RedeTV HQ",
            "model": "3Com 2928",
            "profile": "NETWORK_SWITCH"
        }
        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        with self.assertRaises(ValueError):
            ProvisionOrchestrator.apply_plan(plan_id, self.mock_config)

    @patch("requests.patch")
    @patch("requests.post")
    @patch("requests.get")
    def test_full_plan_approve_apply_verify_pipeline(self, mock_get, mock_post, mock_patch):
        mock_patch_res = MagicMock()
        mock_patch_res.status_code = 200
        mock_patch_res.json.return_value = {"id": 1}
        mock_patch.return_value = mock_patch_res

        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 201
        mock_post_res.json.return_value = {"result": "mock_success", "id": 1}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-lab01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE OfficeConnect 1930 JL685A",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        # 1. PLAN
        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]
        plan_hash = plan["hash"]
        self.assertEqual(plan["status"], "PENDING_APPROVAL")

        # 2. APPROVE
        approved_plan = ProvisionOrchestrator.approve_plan(plan_id, plan_hash)
        self.assertEqual(approved_plan["status"], "APPROVED")

        # 3. APPLY
        apply_res = ProvisionOrchestrator.apply_plan(plan_id, self.mock_config)
        self.assertEqual(apply_res["status"], "APPLIED")
        self.assertIn("results", apply_res)

        # 4. VERIFY & RECONCILE
        verification = ProvisionReconciliationEngine.verify_and_reconcile(
            plan_id, approved_plan, apply_res["results"]
        )

        self.assertEqual(verification["netbox"], "PASS")
        self.assertEqual(verification["zabbix"], "PASS")
        self.assertEqual(verification["librenms"], "PASS")
        self.assertEqual(verification["netdisco"], "PASS")
        self.assertEqual(verification["drift"], 0)
        self.assertEqual(verification["overall"], "PASS")
        self.assertIn("RECONCILIATION STATE: COMPLIANT", verification["formatted_report"])

if __name__ == '__main__':
    unittest.main()
