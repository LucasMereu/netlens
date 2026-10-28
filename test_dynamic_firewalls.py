import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.config_service import ConfigService
from app.services.sophos_service import SophosService
from app.services.wan_monitor_service import WanMonitorService

class TestDynamicFirewallsAndPracas(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_default_firewalls_loaded(self):
        """Verifica se os firewalls padrão (incluindo 10.61.0.250 Brasília) são carregados de ConfigService."""
        appliances = SophosService.get_appliances()
        self.assertIsInstance(appliances, list)
        self.assertGreaterEqual(len(appliances), 3)

        hosts = [a.get("host") for a in appliances]
        self.assertIn("10.1.1.2", hosts)
        self.assertIn("10.61.0.250", hosts)
        self.assertIn("10.11.0.253", hosts)
        self.assertNotIn("10.65.0.250", hosts)

        # Checar se 10.61.0.250 tem use_default_auth e credenciais de SP
        praca_bsb = next((a for a in appliances if a.get("host") == "10.61.0.250"), None)
        self.assertIsNotNone(praca_bsb)
        self.assertTrue(praca_bsb.get("use_default_auth"))
        self.assertEqual(praca_bsb.get("user"), "netlens_api")

    def test_get_appliances_api(self):
        """Testa o endpoint GET /api/firewall/appliances autenticado."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "admin"
            sess["user_role"] = "admin"

        res = self.client.get("/api/firewall/appliances")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("appliances", data)
        hosts = [a["host"] for a in data["appliances"]]
        self.assertIn("10.61.0.250", hosts)
        self.assertNotIn("10.65.0.250", hosts)

    def test_firewall_crud_flow(self):
        """Testa o ciclo de criação, edição e exclusão de um firewall via API REST."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "admin"
            sess["user_role"] = "admin"

        test_host = "10.77.0.250"
        # 1. Criação (POST)
        post_res = self.client.post("/api/firewall/appliances", json={
            "name": "Sophos Praça Teste (F9)",
            "host": test_host,
            "port": "4444",
            "city": "Praça Teste",
            "role": "Gateway de Teste",
            "use_default_auth": True
        })
        self.assertEqual(post_res.status_code, 200)
        post_data = post_res.get_json()
        self.assertTrue(post_data.get("success"))
        fw_id = post_data["appliance"]["id"]

        # 2. Edição (PUT)
        put_res = self.client.put(f"/api/firewall/appliances/{fw_id}", json={
            "city": "Praça Teste Atualizada",
            "role": "Borda & VPN"
        })
        self.assertEqual(put_res.status_code, 200)
        put_data = put_res.get_json()
        self.assertEqual(put_data["appliance"]["city"], "Praça Teste Atualizada")

        # 3. Exclusão (DELETE)
        del_res = self.client.delete(f"/api/firewall/appliances/{fw_id}")
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.get_json()
        self.assertTrue(del_data.get("success"))

    def test_wan_health_praca_selection(self):
        """Verifica se WanMonitorService filtra alvos quando fornecido host da praça."""
        # Se consultar sem host (geral)
        all_data = WanMonitorService.get_wan_health(force=True)
        self.assertIn("links", all_data)

        # Se consultar especificamente para a praça Brasília (10.61.0.250)
        bsb_links = WanMonitorService.get_links_for_host("10.61.0.250")
        self.assertTrue(any(l["target_ip"] == "10.61.0.250" for l in bsb_links))
        self.assertEqual(len(bsb_links), 4)

        # Se consultar especificamente para São Paulo (10.1.1.2)
        sp_links = WanMonitorService.get_links_for_host("10.1.1.2")
        self.assertTrue(len(sp_links) >= 3)

    def test_test_connectivity_endpoint(self):
        """Testa o endpoint de teste prévio de conectividade (/api/firewall/appliances/test)."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "admin"
            sess["user_role"] = "admin"

        # Mock probe para teste controlado
        with patch.object(WanMonitorService, "_probe_icmp", return_value={"alive": True, "packet_loss": 0.0, "rtt_avg": 5.2}):
            res = self.client.post("/api/firewall/appliances/test", json={"host": "10.1.1.2", "port": 4444})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("summary", data)

if __name__ == "__main__":
    unittest.main()
