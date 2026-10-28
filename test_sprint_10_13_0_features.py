"""
Sprint 10.13.0 — Feature Tests
Tests for: F1 (Zabbix SNMP), F2 (UX Post-Provisioning contracts), F3 (Admin CRUD)
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NETLENS_MASTER_KEY", "test_master_key_sprint_10_10_0_super_secure=")

from app import create_app
from app.models.provision_profile import BUILTIN_PROFILES, ProvisionProfile
from app.services.config_service import ConfigService


class TestF1ZabbixSNMPInterface(unittest.TestCase):
    """F1: Zabbix SNMP interface details and macro tests."""

    def test_profile_has_snmp_version_field(self):
        """Verify ProvisionProfile dataclass has snmp_version field."""
        profile = BUILTIN_PROFILES["NETWORK_SWITCH"]
        self.assertTrue(hasattr(profile, 'snmp_version'))
        self.assertEqual(profile.snmp_version, "v2c")

    def test_snmp_profiles_have_correct_version(self):
        """SNMP devices (interface_type=2) should have snmp_version='v2c'."""
        for name, profile in BUILTIN_PROFILES.items():
            if profile.zabbix_interface_type == 2:
                self.assertEqual(profile.snmp_version, "v2c", f"{name} should have snmp_version='v2c'")

    def test_agent_profiles_have_no_snmp(self):
        """Agent devices (interface_type=1) should have snmp_version='none'."""
        for name, profile in BUILTIN_PROFILES.items():
            if profile.zabbix_interface_type == 1:
                self.assertEqual(profile.snmp_version, "none", f"{name} should have snmp_version='none'")

    def test_zabbix_snmp_interface_details(self):
        """Verify ZabbixProvisioner builds interface with details for SNMP type."""
        from app.services.provision_drivers.zabbix_provisioner import ZabbixProvisioner
        import unittest.mock as mock

        mock_auth_response = mock.MagicMock()
        mock_auth_response.json.return_value = {"result": "fake_token"}
        mock_create_response = mock.MagicMock()
        mock_create_response.json.return_value = {"result": {"hostids": ["12345"]}}

        captured_payloads = []

        def mock_post(url, json=None, timeout=None):
            captured_payloads.append(json)
            if json and json.get("method") == "user.login":
                return mock_auth_response
            return mock_create_response

        with mock.patch('app.services.provision_drivers.zabbix_provisioner.requests.post', side_effect=mock_post):
            result = ZabbixProvisioner.provision(
                inp={"hostname": "test-snmp-host", "ip": "10.10.10.1"},
                config={"zabbix": {"url": "http://mock-zabbix", "user": "Admin", "password": "test"}},
                resolved={
                    "interface_type": 2,
                    "port": 161,
                    "snmp_version": "v2c",
                    "group_ids": ["5"],
                    "template_ids": ["10001"],
                    "tags": [{"tag": "Profile", "value": "NETWORK_SWITCH"}]
                },
                action="CREATE",
                snmp_community="myTestCommunity"
            )

        self.assertEqual(result["status"], "PASS")
        host_payload = captured_payloads[1]
        interface = host_payload["params"]["interfaces"][0]

        # Verify SNMP details
        self.assertIn("details", interface)
        self.assertEqual(interface["details"]["version"], 2)
        self.assertEqual(interface["details"]["bulk"], 1)
        self.assertEqual(interface["details"]["community"], "{$SNMP_COMMUNITY}")

    def test_zabbix_snmp_community_macro(self):
        """Verify ZabbixProvisioner sets {$SNMP_COMMUNITY} host macro."""
        from app.services.provision_drivers.zabbix_provisioner import ZabbixProvisioner
        import unittest.mock as mock

        captured_payloads = []
        mock_auth = mock.MagicMock()
        mock_auth.json.return_value = {"result": "token"}
        mock_create = mock.MagicMock()
        mock_create.json.return_value = {"result": {"hostids": ["999"]}}

        def mock_post(url, json=None, timeout=None):
            captured_payloads.append(json)
            if json and json.get("method") == "user.login":
                return mock_auth
            return mock_create

        with mock.patch('app.services.provision_drivers.zabbix_provisioner.requests.post', side_effect=mock_post):
            ZabbixProvisioner.provision(
                inp={"hostname": "test-macro", "ip": "10.10.10.2"},
                config={"zabbix": {"url": "http://mock", "user": "Admin", "password": "p"}},
                resolved={"interface_type": 2, "port": 161, "snmp_version": "v2c", "group_ids": ["2"], "tags": []},
                action="CREATE",
                snmp_community="SecretComm"
            )

        host_payload = captured_payloads[1]
        self.assertIn("macros", host_payload["params"])
        macros = host_payload["params"]["macros"]
        self.assertEqual(len(macros), 1)
        self.assertEqual(macros[0]["macro"], "{$SNMP_COMMUNITY}")
        self.assertEqual(macros[0]["value"], "SecretComm")

    def test_zabbix_agent_no_details(self):
        """Verify Agent interface (type=1) does NOT include details or macros."""
        from app.services.provision_drivers.zabbix_provisioner import ZabbixProvisioner
        import unittest.mock as mock

        captured_payloads = []
        mock_auth = mock.MagicMock()
        mock_auth.json.return_value = {"result": "token"}
        mock_create = mock.MagicMock()
        mock_create.json.return_value = {"result": {"hostids": ["111"]}}

        def mock_post(url, json=None, timeout=None):
            captured_payloads.append(json)
            if json and json.get("method") == "user.login":
                return mock_auth
            return mock_create

        with mock.patch('app.services.provision_drivers.zabbix_provisioner.requests.post', side_effect=mock_post):
            ZabbixProvisioner.provision(
                inp={"hostname": "test-agent", "ip": "10.10.10.3"},
                config={"zabbix": {"url": "http://mock", "user": "Admin", "password": "p"}},
                resolved={"interface_type": 1, "port": 10050, "group_ids": ["2"], "tags": []},
                action="CREATE",
                snmp_community="unused"
            )

        host_payload = captured_payloads[1]
        interface = host_payload["params"]["interfaces"][0]
        self.assertNotIn("details", interface)
        self.assertNotIn("macros", host_payload["params"])


class TestF2ProvisioningAPIContract(unittest.TestCase):
    """F2: Post-provisioning API contract tests."""

    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def test_apply_returns_async_202(self):
        """Verify /apply returns HTTP 202 + QUEUED for approved plan."""
        import unittest.mock as mock

        fake_plan = {
            "plan_id": "PROV-2026-AAAAAAAA",
            "status": "APPROVED",
            "hash": "abc123",
            "approved_plan_hash": "abc123",
            "risk": "LOW",
            "risk_assessment": {"can_apply": True, "risk_score": 10},
            "input": {"hostname": "test", "ip": "1.2.3.4", "site": "Test", "model": "Test"},
            "profile": "NETWORK_SWITCH",
            "operations": [],
            "canonical_identity": {"hostname": "test", "ip": "1.2.3.4", "site": "Test"},
            "_secret_snmp_community": "public",
            "system_actions": {},
            "resolved_objects": {"netbox": {}, "zabbix": {}}
        }

        mock_job = mock.MagicMock()
        mock_job.job_id = "j-test"
        mock_job.plan_id = "PROV-2026-AAAAAAAA"
        mock_job.plan_hash = "abc123"
        mock_job.status = "QUEUED"

        with mock.patch('app.services.provision_orchestrator._PLAN_STORE', {"PROV-2026-AAAAAAAA": fake_plan}):
            with mock.patch('app.services.provision_orchestrator._load_plan_store_into_memory'):
                with mock.patch('app.services.provision_orchestrator._persist_plan_store'):
                    with mock.patch('app.services.job_engine.JobEngine.submit_plan_execution', return_value=mock_job):
                        res = self.client.post('/api/v1/provision/apply',
                            json={"plan_id": "PROV-2026-AAAAAAAA", "plan_hash": "abc123"},
                            content_type='application/json')

        self.assertEqual(res.status_code, 202)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "QUEUED")


class TestF3AdminCRUD(unittest.TestCase):
    """F3: Admin CRUD endpoint tests."""

    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
        ConfigService._config = None

    def test_admin_profiles_list_builtin(self):
        """GET /api/admin/profiles should return builtin profiles."""
        res = self.client.get('/api/admin/profiles')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        profiles = data.get("data", [])
        names = [p["name"] for p in profiles]
        self.assertIn("NETWORK_SWITCH", names)
        self.assertIn("SERVER_LINUX", names)
        for p in profiles:
            if p["name"] in BUILTIN_PROFILES:
                self.assertTrue(p["builtin"])

    def test_admin_profiles_create_custom(self):
        """POST /api/admin/profiles should create custom profile."""
        res = self.client.post('/api/admin/profiles',
            json={
                "name": "TEST_CAMERA",
                "description": "Test Camera Profile",
                "netbox_role_slug": "camera",
                "netbox_object_type": "device",
                "zabbix_groups": ["Cameras"],
                "zabbix_templates": [],
                "zabbix_interface_type": 2,
                "zabbix_port": 161,
                "snmp_version": "v2c",
                "librenms_protocol": "snmp",
                "librenms_version": "v2c",
                "librenms_port": 161,
                "netdisco_discovery_enabled": False,
                "netdisco_protocols": []
            },
            content_type='application/json')
        self.assertIn(res.status_code, [200, 201])
        data = res.get_json()
        self.assertTrue(data.get("success"))

        # Verify it appears in the list
        res2 = self.client.get('/api/admin/profiles')
        profiles = res2.get_json().get("data", [])
        names = [p["name"] for p in profiles]
        self.assertIn("TEST_CAMERA", names)

        # Cleanup
        self.client.delete('/api/admin/profiles/TEST_CAMERA')

    def test_admin_profiles_builtin_readonly(self):
        """DELETE/PUT on builtin profiles should return 403."""
        res_del = self.client.delete('/api/admin/profiles/NETWORK_SWITCH')
        self.assertEqual(res_del.status_code, 403)

        res_put = self.client.put('/api/admin/profiles/NETWORK_SWITCH',
            json={"name": "NETWORK_SWITCH", "description": "hacked"},
            content_type='application/json')
        self.assertEqual(res_put.status_code, 403)

    def test_admin_sites_crud(self):
        """Full CRUD cycle for sites."""
        res = self.client.post('/api/admin/sites',
            json={"name": "Test Lab", "description": "Test laboratory"},
            content_type='application/json')
        self.assertIn(res.status_code, [200, 201])
        site_id = res.get_json().get("site", {}).get("id")
        self.assertIsNotNone(site_id)

        res2 = self.client.get('/api/admin/sites')
        self.assertEqual(res2.status_code, 200)
        sites = res2.get_json().get("data", [])
        site_names = [s["name"] for s in sites]
        self.assertIn("Test Lab", site_names)

        res3 = self.client.delete(f'/api/admin/sites/{site_id}')
        self.assertEqual(res3.status_code, 200)

    def test_admin_models_crud(self):
        """Full CRUD cycle for models."""
        res = self.client.post('/api/admin/models',
            json={"manufacturer": "Cisco", "model": "Catalyst 9300", "default_profile": "NETWORK_SWITCH"},
            content_type='application/json')
        self.assertIn(res.status_code, [200, 201])
        model_id = res.get_json().get("model", {}).get("id")
        self.assertIsNotNone(model_id)

        res2 = self.client.get('/api/admin/models')
        self.assertEqual(res2.status_code, 200)
        models = res2.get_json().get("data", [])
        model_names = [m["model"] for m in models]
        self.assertIn("Catalyst 9300", model_names)

        res3 = self.client.delete(f'/api/admin/models/{model_id}')
        self.assertEqual(res3.status_code, 200)

    def test_admin_endpoints_require_auth(self):
        """Admin endpoints without auth should return 401."""
        client2 = self.app.test_client()
        res = client2.get('/api/admin/profiles')
        self.assertEqual(res.status_code, 401)

        res2 = client2.get('/api/admin/sites')
        self.assertEqual(res2.status_code, 401)

        res3 = client2.get('/api/admin/models')
        self.assertEqual(res3.status_code, 401)

    def test_admin_models_validation(self):
        """POST /api/admin/models without required fields should return 400."""
        res = self.client.post('/api/admin/models',
            json={"manufacturer": "Cisco"},
            content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_admin_sites_validation(self):
        """POST /api/admin/sites without name should return 400."""
        res = self.client.post('/api/admin/sites',
            json={"description": "No name"},
            content_type='application/json')
        self.assertEqual(res.status_code, 400)


class TestF3ConfigServiceAtomic(unittest.TestCase):
    """F3: ConfigService atomic write tests."""

    def test_config_save_creates_backup(self):
        """save_config should create .bak file."""
        bak_path = ConfigService.CONFIG_PATH + ".bak"
        config = ConfigService.load_config()
        ConfigService.save_config(config)
        self.assertTrue(os.path.exists(bak_path))

    def test_config_reload_invalidates_cache(self):
        """reload_config should clear internal cache."""
        ConfigService._config = {"test": "cached"}
        result = ConfigService.reload_config()
        self.assertNotEqual(result.get("test"), "cached")

    def test_config_has_new_sections(self):
        """Config should have custom_profiles, sites, device_models defaults."""
        ConfigService._config = None
        config = ConfigService.load_config()
        self.assertIn("custom_profiles", config)
        self.assertIn("sites", config)
        self.assertIn("device_models", config)
        self.assertIsInstance(config["custom_profiles"], dict)
        self.assertIsInstance(config["sites"], list)
        self.assertIsInstance(config["device_models"], list)


class TestF1ProfileEngineIntegration(unittest.TestCase):
    """F1: Profile engine propagates snmp_version correctly."""

    def test_profile_engine_returns_snmp_version(self):
        """get_profile should return profile with snmp_version."""
        from app.services.provision_profile_engine import ProvisionProfileEngine
        profile = ProvisionProfileEngine.get_profile("NETWORK_SWITCH")
        self.assertEqual(profile.snmp_version, "v2c")

    def test_profile_engine_agent_no_snmp(self):
        """Agent profiles should have snmp_version='none'."""
        from app.services.provision_profile_engine import ProvisionProfileEngine
        profile = ProvisionProfileEngine.get_profile("SERVER_LINUX")
        self.assertEqual(profile.snmp_version, "none")


class TestNetBoxEnhancements(unittest.TestCase):
    """Tests for NetBox VM/Cluster differentiation, resource fields, and custom fields."""

    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def test_get_clusters_endpoint(self):
        """GET /api/v1/provision/clusters returns list of Proxmox clusters."""
        res = self.client.get('/api/v1/provision/clusters')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        clusters = data.get("clusters", [])
        self.assertTrue(len(clusters) > 0)
        first = clusters[0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("type", first)

    def test_netbox_vm_provisioning_payload(self):
        """Verify NetBoxProvisioner creates VM using virtualization endpoints with cluster and custom fields."""
        from app.services.provision_drivers.netbox_provisioner import NetBoxProvisioner
        import unittest.mock as mock

        captured_requests = []

        def mock_post(url, json=None, headers=None, verify=None, timeout=None):
            captured_requests.append({"method": "POST", "url": url, "json": json})
            m = mock.MagicMock()
            m.status_code = 201
            m.json.return_value = {"id": 999}
            return m

        def mock_patch(url, json=None, headers=None, verify=None, timeout=None):
            captured_requests.append({"method": "PATCH", "url": url, "json": json})
            m = mock.MagicMock()
            m.status_code = 200
            m.json.return_value = {"id": 999}
            return m

        with mock.patch('requests.post', side_effect=mock_post):
            with mock.patch('requests.patch', side_effect=mock_patch):
                res = NetBoxProvisioner.provision(
                    inp={"hostname": "vm-test-pve", "ip": "10.10.10.99"},
                    config={"netbox": {"url": "http://mock-netbox", "api_token": "tok"}},
                    resolved={
                        "object_type": "virtualmachine",
                        "cluster_id": 18,
                        "vcpus": 4.0,
                        "memory": 8192,
                        "disk": 100,
                        "custom_fields": {
                            "HD": "100G",
                            "Memoria": "8G",
                            "Processador": "4 Cores",
                            "URL": "http://10.10.10.99:8080/"
                        },
                        "ip_address_with_mask": "10.10.10.99/24"
                    },
                    action="CREATE"
                )

        self.assertEqual(res["status"], "PASS")
        # 1. First POST must be to virtual-machines endpoint
        vm_post = captured_requests[0]
        self.assertIn("/api/virtualization/virtual-machines/", vm_post["url"])
        self.assertEqual(vm_post["json"]["cluster"], 18)
        self.assertEqual(vm_post["json"]["vcpus"], 4.0)
        self.assertEqual(vm_post["json"]["memory"], 8192)
        self.assertEqual(vm_post["json"]["disk"], 100)
        self.assertEqual(vm_post["json"]["custom_fields"]["HD"], "100G")
        self.assertEqual(vm_post["json"]["custom_fields"]["URL"], "http://10.10.10.99:8080/")

        # 2. Second POST must be to virtualization/interfaces/
        iface_post = captured_requests[1]
        self.assertIn("/api/virtualization/interfaces/", iface_post["url"])
        self.assertEqual(iface_post["json"]["virtual_machine"], 999)

        # 3. Third POST must be to ipam/ip-addresses with virtualization.vminterface
        ip_post = captured_requests[2]
        self.assertIn("/api/ipam/ip-addresses/", ip_post["url"])
        self.assertEqual(ip_post["json"]["assigned_object_type"], "virtualization.vminterface")

    def test_netbox_device_provisioning_custom_fields(self):
        """Verify NetBoxProvisioner creates physical Device with custom fields."""
        from app.services.provision_drivers.netbox_provisioner import NetBoxProvisioner
        import unittest.mock as mock

        captured_requests = []

        def mock_post(url, json=None, headers=None, verify=None, timeout=None):
            captured_requests.append({"method": "POST", "url": url, "json": json})
            m = mock.MagicMock()
            m.status_code = 201
            m.json.return_value = {"id": 555}
            return m

        def mock_patch(url, json=None, headers=None, verify=None, timeout=None):
            captured_requests.append({"method": "PATCH", "url": url, "json": json})
            m = mock.MagicMock()
            m.status_code = 200
            m.json.return_value = {"id": 555}
            return m

        with mock.patch('requests.post', side_effect=mock_post):
            with mock.patch('requests.patch', side_effect=mock_patch):
                res = NetBoxProvisioner.provision(
                    inp={"hostname": "sw-core-01", "ip": "10.10.10.50"},
                    config={"netbox": {"url": "http://mock-netbox", "api_token": "tok"}},
                    resolved={
                        "object_type": "device",
                        "device_type_id": 10,
                        "role_id": 2,
                        "site_id": 1,
                        "custom_fields": {
                            "HD": "500G",
                            "Memoria": "16G",
                            "Processador": "8 Cores"
                        },
                        "ip_address_with_mask": "10.10.10.50/24"
                    },
                    action="CREATE"
                )

        self.assertEqual(res["status"], "PASS")
        dev_post = captured_requests[0]
        self.assertIn("/api/dcim/devices/", dev_post["url"])
        self.assertEqual(dev_post["json"]["custom_fields"]["HD"], "500G")
        self.assertEqual(dev_post["json"]["custom_fields"]["Memoria"], "16G")


if __name__ == '__main__':
    unittest.main()
