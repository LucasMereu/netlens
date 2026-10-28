"""
Unit tests for dynamic Zabbix template selection in provisioning flow.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NETLENS_MASTER_KEY", "test_master_key_sprint_10_10_0_super_secure=")

from app import create_app
from app.models.provision_profile import BUILTIN_PROFILES
from app.services.provision_profile_engine import ProvisionProfileEngine
from app.services.provision_drivers.zabbix_provisioner import ZabbixProvisioner

class TestZabbixTemplateSelection(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'

    def test_get_zabbix_templates_endpoint(self):
        """Test GET /api/v1/provision/zabbix-templates returns success and list."""
        resp = self.client.get('/api/v1/provision/zabbix-templates')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('templates', data)
        self.assertIsInstance(data['templates'], list)
        self.assertTrue(len(data['templates']) > 0)
        self.assertTrue(any('Linux' in t['name'] for t in data['templates']))

    def test_engine_resolve_zabbix_with_custom_template(self):
        """Test ProvisionProfileEngine resolves custom template over profile default."""
        profile = BUILTIN_PROFILES["VM_PROXMOX"]
        config = {
            "zabbix": {
                "url": "http://mock-zabbix",
                "user": "Admin",
                "password": "pwd"
            }
        }

        # Mock Zabbix API response
        def mock_post(url, json=None, timeout=None):
            mock_res = MagicMock()
            method = json.get("method") if json else ""
            if method == "user.login":
                mock_res.json.return_value = {"result": "fake-token"}
            elif method == "host.get":
                mock_res.json.return_value = {"result": []}
            elif method == "hostgroup.get":
                mock_res.json.return_value = {"result": [{"groupid": "5", "name": "Discovered hosts"}]}
            elif method == "template.get":
                mock_res.json.return_value = {"result": [{"templateid": "10081", "name": "Template OS Windows by Zabbix agent"}]}
            else:
                mock_res.json.return_value = {"result": []}
            return mock_res

        with patch('app.services.provision_profile_engine.requests.post', side_effect=mock_post):
            resolved = ProvisionProfileEngine.resolve_zabbix_objects(
                config=config,
                profile=profile,
                hostname="srv-win-01",
                ip_address="10.10.10.5",
                custom_template="Template OS Windows by Zabbix agent"
            )

        self.assertEqual(resolved["template_names"], ["Template OS Windows by Zabbix agent"])
        self.assertEqual(resolved["template_ids"], ["10081"])

    @patch("requests.post")
    @patch("requests.get")
    def test_plan_provision_with_custom_template(self, mock_get, mock_post):
        """Test POST /api/v1/provision/plan uses custom template in operations and resolved_objects."""
        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_get_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": [{"templateid": "10643", "name": "01 - WINDOWS"}]}
        mock_post.return_value = mock_post_res

        payload = {
            "hostname": "SRVHAPROXY03",
            "ip": "10.10.10.3",
            "site": "RedeTV HQ",
            "model": "VM",
            "profile": "VM_PROXMOX",
            "zabbix_template": "01 - WINDOWS",
            "cluster": "18"
        }

        with patch('app.services.provision_profile_engine.ProvisionProfileEngine.resolve_zabbix_objects') as mock_resolve:
            mock_resolve.return_value = {
                "group_ids": ["5"],
                "group_names": ["Discovered hosts"],
                "template_ids": ["10643"],
                "template_names": ["01 - WINDOWS"],
                "interface_type": 1,
                "port": 10050,
                "snmp_version": "none",
                "host_status": "NEW",
                "tags": []
            }

            resp = self.client.post('/api/v1/provision/plan', json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))
            plan = data.get("plan")
            self.assertIsNotNone(plan)

            # Check that custom template was passed to resolve_zabbix_objects
            mock_resolve.assert_called_once()
            _, kwargs = mock_resolve.call_args
            self.assertEqual(kwargs.get("custom_template"), "01 - WINDOWS")
            # Check plan operations
            zabbix_op = next((op for op in plan["operations"] if op["system"] == "Zabbix"), None)
            self.assertIsNotNone(zabbix_op)
            self.assertIn("01 - WINDOWS", zabbix_op["details"]["templates"])
            self.assertEqual(plan["input"]["zabbix_template"], "01 - WINDOWS")

    def test_zabbix_provisioner_returns_fail_on_host_create_error(self):
        """Regression test for BUG-001: Ensure ZabbixProvisioner returns FAIL when host.create returns unexpected error."""
        inp = {"hostname": "srv-test-fail", "ip": "10.0.0.99"}
        config = {"zabbix": {"url": "http://mock-zabbix", "user": "Admin", "password": "pwd"}}
        resolved = {"group_ids": ["2"], "template_ids": ["99999"], "interface_type": 1, "port": 10050}

        def mock_post(url, json=None, timeout=None):
            mock_res = MagicMock()
            method = json.get("method") if json else ""
            if method == "user.login":
                mock_res.json.return_value = {"result": "fake-token"}
            elif method == "host.create":
                mock_res.json.return_value = {
                    "error": {
                        "code": -32602,
                        "message": "Invalid params.",
                        "data": "Template with templateid '99999' does not exist."
                    }
                }
            return mock_res

        with patch('app.services.provision_drivers.zabbix_provisioner.requests.post', side_effect=mock_post):
            result = ZabbixProvisioner.provision(inp=inp, config=config, resolved=resolved, action="CREATE")

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Zabbix host.create falhou", result["message"])
        self.assertIn("Template with templateid '99999' does not exist", result["message"])

    def test_zabbix_provisioner_returns_pass_on_host_already_exists(self):
        """Ensure ZabbixProvisioner returns PASS and runs ensure_snmp_interface when host already exists."""
        inp = {"hostname": "srv-test-exists", "ip": "10.0.0.100"}
        config = {"zabbix": {"url": "http://mock-zabbix", "user": "Admin", "password": "pwd"}}
        resolved = {"group_ids": ["2"], "template_ids": ["10001"], "interface_type": 2, "port": 161}

        def mock_post(url, json=None, timeout=None):
            mock_res = MagicMock()
            method = json.get("method") if json else ""
            if method == "user.login":
                mock_res.json.return_value = {"result": "fake-token"}
            elif method == "host.create":
                mock_res.json.return_value = {
                    "error": {
                        "code": -32602,
                        "message": "Invalid params.",
                        "data": "Host with the same name 'srv-test-exists' already exists."
                    }
                }
            elif method == "host.get":
                mock_res.json.return_value = {"result": [{"hostid": "12345", "interfaces": []}]}
            else:
                mock_res.json.return_value = {"result": {}}
            return mock_res

        with patch('app.services.provision_drivers.zabbix_provisioner.requests.post', side_effect=mock_post):
            result = ZabbixProvisioner.provision(inp=inp, config=config, resolved=resolved, action="CREATE")

        self.assertEqual(result["status"], "PASS")
        self.assertIn("Host existente", result["message"])

if __name__ == '__main__':
    unittest.main()
