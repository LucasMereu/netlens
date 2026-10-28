import unittest
from unittest.mock import patch, MagicMock

from app.models.provision_dependency import CanonicalHostIdentity, DependencyStatus
from app.services.provision_dependency_engine import ProvisionDependencyEngine

class TestProvisionDependencyEngine(unittest.TestCase):

    def setUp(self):
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

    @patch("requests.get")
    def test_netbox_device_absent(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"count": 0, "results": []}
        mock_get.return_value = mock_res

        res = ProvisionDependencyEngine.discover_netbox(self.canonical, self.mock_config)
        self.assertEqual(res.status, DependencyStatus.ABSENT)
        self.assertEqual(res.system, "NetBox")

    @patch("requests.get")
    def test_netbox_device_existing(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"count": 1, "results": [{"id": 320, "name": "sw-hpe-lab01"}]}
        mock_get.return_value = mock_res

        res = ProvisionDependencyEngine.discover_netbox(self.canonical, self.mock_config)
        self.assertEqual(res.status, DependencyStatus.EXISTING)
        self.assertEqual(res.object_id, 320)

    @patch("requests.post")
    def test_zabbix_host_ip_conflict_blocks_plan(self, mock_post):
        # User login mock
        login_res = MagicMock()
        login_res.json.return_value = {"result": "auth_token_123"}
        
        # Host get mock (existing host with DIFFERENT IP 10.11.0.99 instead of 10.11.0.250)
        host_res = MagicMock()
        host_res.json.return_value = {
            "result": [
                {
                    "hostid": "10050",
                    "host": "sw-hpe-lab01",
                    "interfaces": [{"ip": "10.11.0.99"}]
                }
            ]
        }
        mock_post.side_effect = [login_res, host_res]

        res = ProvisionDependencyEngine.discover_zabbix(self.canonical, self.mock_config)
        self.assertEqual(res.status, DependencyStatus.CONFLICT)
        self.assertTrue(len(res.conflicts) > 0)

    def test_build_dependency_dag(self):
        dag = ProvisionDependencyEngine.build_dependency_dag(self.canonical)
        self.assertEqual(len(dag), 5)
        self.assertEqual(dag[0]["system"], "NetBox")
        self.assertIn("PROV-sw-hpe-lab01-NB-DEVICE", dag[1]["depends_on"])

if __name__ == '__main__':
    unittest.main()
