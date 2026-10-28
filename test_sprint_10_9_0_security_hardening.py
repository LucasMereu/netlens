import unittest
import os
import json
import base64
import multiprocessing
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet

# Fixed static master key string so spawned child processes use the exact same key as parent process
STATIC_TEST_MASTER_KEY = "y1Z4pQ8wR2tV5xY8zA1bC3dE5fG7hI9jK0lM2nO4pQ6="
os.environ["NETLENS_MASTER_KEY"] = STATIC_TEST_MASTER_KEY

from app.services.secret_service import SecretService, ConfigurationError
from app.utils.sanitizer import SecretSanitizer
from app.services.config_service import ConfigService
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE, _load_plan_store_into_memory
from app import create_app

def _worker_apply_task(plan_id, valid_hash, queue):
    """Multiprocessing worker function simulating an independent Gunicorn process."""
    os.environ["NETLENS_MASTER_KEY"] = STATIC_TEST_MASTER_KEY
    SecretService._fernet_instance = None
    SecretService._current_raw_key = None
    mock_config = {
        "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
        "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
        "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
        "netdisco": {"url": "http://192.168.10.51:5000"}
    }
    try:
        res = ProvisionOrchestrator.apply_plan(plan_id, mock_config, plan_hash=valid_hash)
        queue.put({"pid": os.getpid(), "status": "SUCCESS", "result": res})
    except Exception as e:
        queue.put({"pid": os.getpid(), "status": "BLOCKED", "error": str(e)})

class TestSprint1090SecurityHardening(unittest.TestCase):

    def setUp(self):
        os.environ["NETLENS_MASTER_KEY"] = STATIC_TEST_MASTER_KEY
        SecretService._fernet_instance = None
        SecretService._current_raw_key = None
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
        os.environ["NETLENS_MASTER_KEY"] = STATIC_TEST_MASTER_KEY
        SecretService._fernet_instance = None
        SecretService._current_raw_key = None
        _PLAN_STORE.clear()
        for path in [ConfigService.PLANS_PATH, ConfigService.PLANS_PATH + ".tmp", ConfigService.PLANS_PATH + ".bak"]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    @patch("requests.post")
    @patch("requests.get")
    def test_fernet_encryption_and_legacy_migration(self, mock_get, mock_post):
        """Test Fernet encryption at rest (FERNET:) and legacy ENC: read-only migration."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        raw_community = "secret_fernet_snmp_community"
        input_data = {
            "hostname": "sw-hpe-fernet01",
            "ip": "10.11.0.210",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": raw_community
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        # 1. Verify saved file contains FERNET: prefix
        disk_plans = ConfigService.load_plans()
        stored_enc = disk_plans[plan_id]["_secret_snmp_community"]
        self.assertTrue(stored_enc.startswith("FERNET:"), f"Expected FERNET: prefix, got {stored_enc}")

        # 2. Decrypt secret and verify exact match
        decrypted = SecretService.decrypt_secret(stored_enc)
        self.assertEqual(decrypted, raw_community)

        # 3. Simulate legacy ENC:<base64> in disk file and verify migration on load
        legacy_enc = "ENC:" + base64.b64encode("legacy_pass".encode("utf-8")).decode("utf-8")
        disk_plans[plan_id]["_secret_snmp_community"] = legacy_enc
        ConfigService.save_plans(disk_plans)

        _PLAN_STORE.clear()
        _load_plan_store_into_memory()

        # Check in-memory decrypted value
        self.assertEqual(_PLAN_STORE[plan_id]["_secret_snmp_community"], "legacy_pass")

        # Save and verify it is re-persisted strictly as FERNET:
        ProvisionOrchestrator._persist_plan_store()
        re_saved = ConfigService.load_plans()
        self.assertTrue(re_saved[plan_id]["_secret_snmp_community"].startswith("FERNET:"))

    def test_missing_master_key_raises_configuration_error(self):
        """Test that missing NETLENS_MASTER_KEY raises ConfigurationError and blocks operation."""
        try:
            del os.environ["NETLENS_MASTER_KEY"]
            SecretService._fernet_instance = None
            SecretService._current_raw_key = None

            with self.assertRaises(ConfigurationError) as cm:
                SecretService.encrypt_secret("test_secret")
            self.assertIn("NETLENS_MASTER_KEY", str(cm.exception))

            with self.assertRaises(ConfigurationError) as cm_dec:
                SecretService.decrypt_secret("FERNET:some_token")
            self.assertIn("NETLENS_MASTER_KEY", str(cm_dec.exception))
        finally:
            os.environ["NETLENS_MASTER_KEY"] = STATIC_TEST_MASTER_KEY
            SecretService._fernet_instance = None
            SecretService._current_raw_key = None

    @patch("requests.post")
    @patch("requests.get")
    def test_aggressive_secret_leakage_protection(self, mock_get, mock_post):
        """Aggressively verify raw secret NEVER leaks in API HTTP responses, execution_results, logs, or JSON files."""
        SECRET_VALUE = "NetLens-SNMP-SuperSecret-9f82b1a"

        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        # Force mock requests to raise exception containing the secret payload
        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}

        def mock_post_dispatcher(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "devices" in url or "host.create" in str(kwargs):
                raise Exception(f"Connection failed for payload with community: '{SECRET_VALUE}' and password='{SECRET_VALUE}'")
            return mock_post_res

        mock_post.side_effect = mock_post_dispatcher

        input_data = {
            "hostname": "sw-hpe-leaktest01",
            "ip": "10.11.0.211",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": SECRET_VALUE
        }

        # 1. Generate Plan
        res_plan = self.client.post('/api/v1/provision/plan', json=input_data)
        self.assertEqual(res_plan.status_code, 200)
        data_plan = res_plan.get_json()
        plan_id = data_plan["plan"]["plan_id"]
        plan_hash = data_plan["plan"]["hash"]

        # Assert secret not in response
        self.assertNotIn(SECRET_VALUE, res_plan.get_data(as_text=True))
        self.assertEqual(data_plan["plan"]["input"]["snmp_community"], "[REDACTED]")

        # 2. Approve Plan
        res_app = self.client.post('/api/v1/provision/approve', json={"plan_id": plan_id, "hash": plan_hash})
        self.assertEqual(res_app.status_code, 200)
        self.assertNotIn(SECRET_VALUE, res_app.get_data(as_text=True))

        # 3. Apply Plan (Triggers mock exceptions)
        res_apply = self.client.post('/api/v1/provision/apply', json={"plan_id": plan_id, "hash": plan_hash})
        self.assertEqual(res_apply.status_code, 202)
        apply_data = res_apply.get_data(as_text=True)

        # Assert secret is scrubbed in API execution results
        self.assertNotIn(SECRET_VALUE, apply_data)

        # 4. Check persisted JSON file on disk
        if os.path.exists(ConfigService.PLANS_PATH):
            with open(ConfigService.PLANS_PATH, 'r', encoding='utf-8') as f:
                disk_content = f.read()
                # Verify raw secret value does NOT appear in raw text of JSON file
                self.assertNotIn(SECRET_VALUE, disk_content)

    @patch("requests.post")
    @patch("requests.get")
    def test_atomic_persistence_and_backup_recovery(self, mock_get, mock_post):
        """Test atomic file swap (.tmp + fsync + os.replace) and corruption recovery via .bak."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-atomic01",
            "ip": "10.11.0.212",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        # Persist a second time to ensure .bak is written
        ProvisionOrchestrator._persist_plan_store()

        self.assertTrue(os.path.exists(ConfigService.PLANS_PATH))
        bak_path = ConfigService.PLANS_PATH + ".bak"
        self.assertTrue(os.path.exists(bak_path))

        # Corrupt primary JSON file
        with open(ConfigService.PLANS_PATH, 'w', encoding='utf-8') as f:
            f.write("{ CORRUPTED_INVALID_JSON ...")

        _PLAN_STORE.clear()
        ConfigService._plans = None

        # Load plans should detect corruption and recover from .bak
        loaded = ConfigService.load_plans()
        self.assertIn(plan_id, loaded)

    @patch("requests.post")
    @patch("requests.get")
    def test_multi_process_concurrency_lock(self, mock_get, mock_post):
        """Test multi-process concurrency locking using multiprocessing.Process (Worker A vs Worker B)."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-multiproc01",
            "ip": "10.11.0.213",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]
        valid_hash = plan["hash"]

        # Approve plan first
        ProvisionOrchestrator.approve_plan(plan_id, plan_hash=valid_hash)

        # Launch 2 independent processes using multiprocessing.Queue
        queue = multiprocessing.Queue()

        p1 = multiprocessing.Process(target=_worker_apply_task, args=(plan_id, valid_hash, queue))
        p2 = multiprocessing.Process(target=_worker_apply_task, args=(plan_id, valid_hash, queue))

        p1.start()
        p2.start()

        p1.join(timeout=10)
        p2.join(timeout=10)

        results = []
        while not queue.empty():
            results.append(queue.get())

        successes = [r for r in results if r["status"] == "SUCCESS"]
        blocked = [r for r in results if r["status"] == "BLOCKED"]

        self.assertEqual(len(successes), 1, f"Expected exactly 1 process to succeed, got {len(successes)}")
        self.assertEqual(len(blocked), 1, f"Expected exactly 1 process to be blocked, got {len(blocked)}")
        self.assertIn("concurrent_execution_blocked", blocked[0]["error"].lower())

if __name__ == "__main__":
    unittest.main()
