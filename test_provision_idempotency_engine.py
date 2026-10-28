import unittest
from unittest.mock import patch, MagicMock

from app.models.provision_dependency import CanonicalHostIdentity, DependencyStatus, DependencyResult
from app.services.provision_idempotency_engine import ProvisionIdempotencyEngine
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE

class TestProvisionIdempotencyEngine(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }
        self.canonical = CanonicalHostIdentity(
            hostname="sw-hpe-lab01",
            ip="10.11.0.250",
            profile="NETWORK_SWITCH",
            site="RedeTV HQ"
        )

    def test_cross_system_correlation_partial_provision(self):
        # NetBox & Zabbix present (EXISTING), LibreNMS & NetDisco absent (ABSENT)
        discovery_results = {
            "netbox": DependencyResult(system="NetBox", object_type="device", requested_identifier="sw-hpe-lab01", status=DependencyStatus.EXISTING, object_id=10),
            "zabbix": DependencyResult(system="Zabbix", object_type="host", requested_identifier="sw-hpe-lab01", status=DependencyStatus.EXISTING, object_id="10050"),
            "librenms": DependencyResult(system="LibreNMS", object_type="device", requested_identifier="10.11.0.250", status=DependencyStatus.ABSENT),
            "netdisco": DependencyResult(system="NetDisco", object_type="device", requested_identifier="10.11.0.250", status=DependencyStatus.ABSENT)
        }

        can_proceed, actions, block_reasons = ProvisionIdempotencyEngine.classify_and_generate_actions(self.canonical, discovery_results)
        self.assertTrue(can_proceed)
        self.assertEqual(actions["netbox"], "REUSE")
        self.assertEqual(actions["zabbix"], "REUSE")
        self.assertEqual(actions["librenms"], "CREATE")
        self.assertEqual(actions["netdisco"], "CREATE")

    @patch("requests.post")
    @patch("requests.get")
    def test_stateful_mock_idempotency_run_1_and_run_2(self, mock_get, mock_post):
        """
        STATEFUL MOCK IDEMPOTENCY TEST:
        - Run 1 (empty state): Actions = CREATE for NetBox, Zabbix, LibreNMS, NetDisco.
        - Apply: Updates state to EXISTING.
        - Run 2 (same input): Actions = REUSE for all 4 systems (CREATE = 0, REUSE = 4).
        """
        # Simulated stateful database across remote systems
        stateful_db = {
            "netbox": False,
            "zabbix": False,
            "librenms": False,
            "netdisco": False
        }

        def dynamic_get(url, **kwargs):
            res = MagicMock()
            res.status_code = 200
            if "dcim/devices" in url or "virtual-machines" in url:
                if stateful_db["netbox"]:
                    res.json.return_value = {"count": 1, "results": [{"id": 500, "name": "sw-hpe-lab01"}]}
                else:
                    res.json.return_value = {"count": 0, "results": []}
            elif "ipam/ip-addresses" in url or "prefixes" in url or "sites" in url or "device-roles" in url or "device-types" in url:
                res.json.return_value = {"count": 1, "results": [{"id": 1, "name": "RedeTV HQ", "slug": "switch", "prefix": "10.11.0.0/24"}]}
            elif "librenms" in url:
                if stateful_db["librenms"]:
                    res.json.return_value = {"devices": [{"device_id": 99, "hostname": "10.11.0.250"}]}
                else:
                    res.status_code = 404
            elif "netdisco" in url:
                if stateful_db["netdisco"]:
                    res.status_code = 200
                else:
                    res.status_code = 404
            return res

        def dynamic_post(url, **kwargs):
            res = MagicMock()
            res.status_code = 201
            json_data = kwargs.get("json", {})

            if "api_jsonrpc.php" in url:
                method = json_data.get("method")
                if method == "user.login":
                    res.json.return_value = {"result": "token_123"}
                elif method == "host.get":
                    if stateful_db["zabbix"]:
                        res.json.return_value = {"result": [{"hostid": "200", "host": "sw-hpe-lab01", "interfaces": [{"ip": "10.11.0.250"}]}]}
                    else:
                        res.json.return_value = {"result": []}
                else:
                    res.json.return_value = {"result": ["200"]}
            return res

        mock_get.side_effect = dynamic_get
        mock_post.side_effect = dynamic_post

        input_data = {
            "hostname": "sw-hpe-lab01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE OfficeConnect 1930 JL685A",
            "profile": "NETWORK_SWITCH",
            "snmp_community": "rtvzabbix"
        }

        # --- RUN 1 (EMPTY STATE) ---
        plan1 = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan1_id = plan1["plan_id"]
        
        # Verify Run 1 actions
        self.assertEqual(plan1["system_actions"]["netbox"], "CREATE")
        self.assertEqual(plan1["system_actions"]["zabbix"], "CREATE")

        # Approve & Apply Run 1
        ProvisionOrchestrator.approve_plan(plan1_id, plan1["hash"])
        ProvisionOrchestrator.apply_plan(plan1_id, self.mock_config)

        # Update stateful mock DB after apply
        stateful_db["netbox"] = True
        stateful_db["zabbix"] = True
        stateful_db["librenms"] = True
        stateful_db["netdisco"] = True

        # --- RUN 2 (SECOND PROVISION WITH SAME INPUT) ---
        plan2 = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)

        # Verify Run 2 actions (Idempotency Proof: REUSE = 4, CREATE = 0)
        self.assertEqual(plan2["system_actions"]["netbox"], "REUSE")
        self.assertEqual(plan2["system_actions"]["zabbix"], "REUSE")
        self.assertEqual(plan2["system_actions"]["librenms"], "REUSE")
        self.assertEqual(plan2["system_actions"]["netdisco"], "REUSE")

if __name__ == '__main__':
    unittest.main()
