import os
import inspect
import unittest
import uuid
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.config_service import ConfigService
from app.services.job_store import JobStore
from app.services.job_engine import JobEngine
from app.models.provision_job import ProvisionJob, JobStatus

class TestSprint10120Refactor(unittest.TestCase):
    """
    Hardening Test Suite for Sprint 10.12.0:
    1. No hardcoded service fallback IPs in app/services/
    2. No hardcoded fallback IPs in app/routes/status.py and dell.py
    3. Atomic job transition prevents TOCTOU races
    4. Lazy backend initialization in JobEngine
    5. POST /api/v1/provision/apply returns 202 Accepted and QUEUED without synthetic result
    """

    def setUp(self):
        os.environ['NETLENS_MASTER_KEY'] = 'test_master_key_sprint_10_10_0_super_secure='
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def test_1_no_hardcoded_service_ips_in_services(self):
        """Test 1: Recursively scan app/services/ for hardcoded fallback IPs."""
        services_dir = os.path.join(os.path.dirname(__file__), "app", "services")
        patterns = ['192.168.10.235', '192.168.10.108', '192.168.10.51', '192.168.10.50']
        hits = []

        for root, dirs, files in os.walk(services_dir):
            for file in files:
                if file.endswith(".py"):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        for line_no, line in enumerate(f, 1):
                            for pat in patterns:
                                if pat in line and not line.strip().startswith("#"):
                                    hits.append(f"{file}:{line_no} -> {line.strip()}")

        self.assertEqual(len(hits), 0, f"Found hardcoded fallback IPs in services: {hits}")

    def test_2_no_hardcoded_ips_in_routes(self):
        """Test 2: Verify no hardcoded service IPs in status.py and dell.py."""
        routes_dir = os.path.join(os.path.dirname(__file__), "app", "routes")
        target_files = ["status.py", "dell.py"]
        patterns = ['192.168.10.235', '192.168.10.108', '192.168.10.51', '192.168.10.50', '10.11.0.248', '10.11.0.249', '10.11.0.251']
        hits = []

        for filename in target_files:
            path = os.path.join(routes_dir, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    for line_no, line in enumerate(f, 1):
                        for pat in patterns:
                            if pat in line and not line.strip().startswith("#"):
                                hits.append(f"{filename}:{line_no} -> {line.strip()}")

        self.assertEqual(len(hits), 0, f"Found hardcoded IPs in routes: {hits}")

    def test_3_atomic_job_transition_prevents_toctou(self):
        """Test 3: JobStore.atomic_transition atomically guards status transitions."""
        job_id = f"job_test_toctou_{uuid.uuid4().hex[:8]}"
        job = ProvisionJob(
            job_id=job_id,
            plan_id="PROV-TEST-TOCTOU",
            plan_hash="hash_toctou_123",
            status=JobStatus.QUEUED
        )
        JobStore.save_job(job)

        # 1. Transition with wrong expected status should fail (return None)
        blocked = JobStore.atomic_transition(job_id, [JobStatus.CANCELLED.value], JobStatus.RUNNING.value)
        self.assertIsNone(blocked)
        current = JobStore.get_job(job_id)
        self.assertEqual(current.status, JobStatus.QUEUED.value)

        # 2. Transition with matching status should succeed
        succeeded = JobStore.atomic_transition(
            job_id,
            [JobStatus.QUEUED.value],
            JobStatus.RUNNING.value,
            updater_fn=lambda j: setattr(j, 'worker_id', 'test_worker_1')
        )
        self.assertIsNotNone(succeeded)
        self.assertEqual(succeeded.status, JobStatus.RUNNING.value)
        self.assertEqual(succeeded.worker_id, 'test_worker_1')

        # 3. Subsequent transition with QUEUED should fail since it is now RUNNING
        second_attempt = JobStore.atomic_transition(job_id, [JobStatus.QUEUED.value], JobStatus.RUNNING.value)
        self.assertIsNone(second_attempt)

    def test_4_lazy_backend_initialization(self):
        """Test 4: JobEngine uses lazy initialization for InProcessExecutionBackend."""
        from app.services.inprocess_execution_backend import InProcessExecutionBackend

        # Verify class attribute backend is NOT an instantiated InProcessExecutionBackend
        self.assertFalse(
            hasattr(JobEngine, 'backend') and isinstance(getattr(JobEngine, 'backend'), InProcessExecutionBackend),
            "JobEngine.backend should not be instantiated at class import time."
        )

        # Verify _backend and _get_backend exist
        self.assertTrue(hasattr(JobEngine, '_get_backend'))
        self.assertTrue(callable(getattr(JobEngine, '_get_backend')))
        
        # Verify call returns InProcessExecutionBackend
        backend_inst = JobEngine._get_backend()
        self.assertIsInstance(backend_inst, InProcessExecutionBackend)

    @patch("requests.patch")
    @patch("requests.post")
    @patch("requests.get")
    def test_5_apply_endpoint_returns_queued_not_applied(self, mock_get, mock_post, mock_patch):
        """Test 5: POST /api/v1/provision/apply returns 202 Accepted, QUEUED status, async true, no synthetic result."""
        res_get = MagicMock()
        res_get.status_code = 200
        res_get.json.return_value = {"results": []}
        mock_get.return_value = res_get

        res_post = MagicMock()
        res_post.status_code = 200
        res_post.json.return_value = {"result": "token123", "id": 1}
        mock_post.return_value = res_post

        # 1. Create a plan
        plan_res = self.client.post('/api/v1/provision/plan', json={
            "hostname": f"sw-refactor-{uuid.uuid4().hex[:4]}",
            "ip": "10.11.4.210",
            "site": "RedeTV HQ",
            "model": "PowerSwitch S4148F-ON",
            "profile": "switch-core-dell",
            "snmp_community": "secret_comm"
        })
        self.assertEqual(plan_res.status_code, 200)
        plan_data = plan_res.get_json()["plan"]
        plan_id = plan_data["plan_id"]
        plan_hash = plan_data["hash"]

        # 2. Approve plan
        app_res = self.client.post('/api/v1/provision/approve', json={"plan_id": plan_id, "hash": plan_hash})
        self.assertEqual(app_res.status_code, 200)

        # 3. Apply plan
        apply_res = self.client.post('/api/v1/provision/apply', json={"plan_id": plan_id, "hash": plan_hash})
        self.assertEqual(apply_res.status_code, 202)
        apply_json = apply_res.get_json()

        self.assertTrue(apply_json["success"])
        self.assertEqual(apply_json["status"], "QUEUED")
        self.assertTrue(apply_json.get("async", False))
        self.assertIn("job_id", apply_json)
        self.assertIn("message", apply_json)
        self.assertNotIn("result", apply_json)

if __name__ == '__main__':
    unittest.main()
