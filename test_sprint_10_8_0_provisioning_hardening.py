import unittest
import os
import json
from unittest.mock import patch, MagicMock
from app.services.config_service import ConfigService
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE, _load_plan_store_into_memory
from app import create_app

class TestSprint1080ProvisioningHardening(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def tearDown(self):
        _PLAN_STORE.clear()
        if os.path.exists(ConfigService.PLANS_PATH):
            try:
                os.remove(ConfigService.PLANS_PATH)
            except Exception:
                pass

    @patch("requests.post")
    @patch("requests.get")
    def test_plan_store_persistence_and_reload(self, mock_get, mock_post):
        """Test persistence of _PLAN_STORE across process restart / reload."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-persist01",
            "ip": "10.11.0.251",
            "site": "RedeTV HQ",
            "model": "HPE OfficeConnect 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "secret_community_pass"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]
        plan_hash = plan["hash"]

        self.assertIn(plan_id, _PLAN_STORE)

        # Clear in-memory store and reload from disk
        _PLAN_STORE.clear()
        self.assertNotIn(plan_id, _PLAN_STORE)

        _load_plan_store_into_memory()
        self.assertIn(plan_id, _PLAN_STORE)
        reloaded_plan = ProvisionOrchestrator.get_plan(plan_id)
        self.assertIsNotNone(reloaded_plan)
        self.assertEqual(reloaded_plan["hash"], plan_hash)
        self.assertEqual(reloaded_plan["input"]["snmp_community"], "[REDACTED]")

    @patch("requests.post")
    @patch("requests.get")
    def test_secret_obfuscation_on_disk(self, mock_get, mock_post):
        """Test that secrets are obfuscated on disk (ENC:...) and redacted in public outputs."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-secret01",
            "ip": "10.11.0.252",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "super_secret_snmp"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        # Check raw saved structure on disk
        saved_plans = ConfigService.load_plans()
        self.assertIn(plan_id, saved_plans)
        raw_saved_plan = saved_plans[plan_id]
        raw_community = raw_saved_plan.get("_secret_snmp_community", "")
        self.assertTrue(raw_community.startswith(("FERNET:", "ENC:")), f"Expected internal secret to start with FERNET: or ENC:, got {raw_community}")

        # Check public get_plan() returns [REDACTED]
        public_plan = ProvisionOrchestrator.get_plan(plan_id)
        self.assertEqual(public_plan["input"]["snmp_community"], "[REDACTED]")

    @patch("requests.post")
    @patch("requests.get")
    def test_tamper_detection_blocks_approval_and_apply(self, mock_get, mock_post):
        """Test that tampered hash blocks approval and application."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-tamper01",
            "ip": "10.11.0.253",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]
        valid_hash = plan["hash"]
        tampered_hash = "0000000000000000000000000000000000000000000000000000000000000000"

        # Attempt approval with tampered hash
        with self.assertRaises(ValueError) as cm:
            ProvisionOrchestrator.approve_plan(plan_id, plan_hash=tampered_hash)
        self.assertIn("hash", str(cm.exception).lower())

        # Approve plan correctly first
        ProvisionOrchestrator.approve_plan(plan_id, plan_hash=valid_hash)

        # Attempt apply with tampered hash
        with self.assertRaises(ValueError) as cm_apply:
            ProvisionOrchestrator.apply_plan(plan_id, self.mock_config, plan_hash=tampered_hash)
        self.assertIn("hash", str(cm_apply.exception).lower())

    @patch("requests.post")
    @patch("requests.get")
    def test_quad_validation_on_apply(self, mock_get, mock_post):
        """Test quad-validation requirements for plan execution."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-quad01",
            "ip": "10.11.0.254",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]
        valid_hash = plan["hash"]

        # 1. Unapproved plan fails apply
        with self.assertRaises(ValueError) as cm:
            ProvisionOrchestrator.apply_plan(plan_id, self.mock_config, plan_hash=valid_hash)
        self.assertIn("aprovado antes da execução", str(cm.exception).lower())

        # 2. Approve plan with correct hash
        approved = ProvisionOrchestrator.approve_plan(plan_id, plan_hash=valid_hash)
        self.assertEqual(approved["status"], "APPROVED")

        # 3. Apply approved plan succeeds
        applied = ProvisionOrchestrator.apply_plan(plan_id, self.mock_config, plan_hash=valid_hash)
        self.assertEqual(applied["status"], "APPLIED")

        # 4. Re-applying already applied plan fails
        with self.assertRaises(ValueError) as cm_reapply:
            ProvisionOrchestrator.apply_plan(plan_id, self.mock_config, plan_hash=valid_hash)
        self.assertIn("aplicado", str(cm_reapply.exception).lower())

    @patch("requests.post")
    @patch("requests.get")
    def test_flask_provisioning_api_endpoints(self, mock_get, mock_post):
        """Test Flask API endpoints /api/v1/provision/* with full JSON contract."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        # 1. POST /api/v1/provision/plan
        res_plan = self.client.post('/api/v1/provision/plan', json={
            "hostname": "sw-hpe-api01",
            "ip": "10.11.0.255",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "secret_community"
        })
        self.assertEqual(res_plan.status_code, 200)
        data_plan = res_plan.get_json()
        self.assertTrue(data_plan["success"])
        plan_id = data_plan["plan"]["plan_id"]
        plan_hash = data_plan["plan"]["hash"]

        # Ensure secret is redacted in API output
        self.assertEqual(data_plan["plan"]["input"]["snmp_community"], "[REDACTED]")

        # 2. POST /api/v1/provision/approve
        res_app = self.client.post('/api/v1/provision/approve', json={
            "plan_id": plan_id,
            "hash": plan_hash
        })
        self.assertEqual(res_app.status_code, 200)
        data_app = res_app.get_json()
        self.assertTrue(data_app["success"])
        self.assertEqual(data_app["plan"]["status"], "APPROVED")

        # 3. POST /api/v1/provision/apply
        res_apply = self.client.post('/api/v1/provision/apply', json={
            "plan_id": plan_id,
            "hash": plan_hash
        })
        self.assertEqual(res_apply.status_code, 202)
        data_apply = res_apply.get_json()
        self.assertTrue(data_apply["success"])
        self.assertEqual(data_apply["status"], "QUEUED")
        self.assertTrue(data_apply.get("async", False))

if __name__ == "__main__":
    unittest.main()
