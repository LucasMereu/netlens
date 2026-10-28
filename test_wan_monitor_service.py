import unittest
from unittest.mock import patch
from app.services.wan_monitor_service import WanMonitorService

class TestWanMonitorService(unittest.TestCase):

    def test_classify_sla_down(self):
        probe = {"alive": False, "packet_loss": 100.0, "rtt_min": 0.0, "rtt_avg": 0.0, "rtt_max": 0.0, "jitter": 0.0}
        sla = WanMonitorService._classify_sla(probe, baseline_rtt=10.0)
        self.assertEqual(sla["status"], "DOWN")
        self.assertTrue(sla["alert"])
        self.assertEqual(sla["badge"], "danger")

    def test_classify_sla_critical_packet_loss(self):
        probe = {"alive": True, "packet_loss": 15.0, "rtt_min": 10.0, "rtt_avg": 20.0, "rtt_max": 35.0, "jitter": 5.0}
        sla = WanMonitorService._classify_sla(probe, baseline_rtt=10.0)
        self.assertEqual(sla["status"], "CRITICAL")
        self.assertTrue(sla["alert"])
        self.assertIn("Perda de pacotes crítica", sla["reason"])

    def test_classify_sla_critical_high_latency(self):
        probe = {"alive": True, "packet_loss": 0.0, "rtt_min": 150.0, "rtt_avg": 210.0, "rtt_max": 300.0, "jitter": 10.0}
        sla = WanMonitorService._classify_sla(probe, baseline_rtt=10.0)
        self.assertEqual(sla["status"], "CRITICAL")
        self.assertTrue(sla["alert"])
        self.assertIn("Latência estourada", sla["reason"])

    def test_classify_sla_degraded_moderate_loss(self):
        probe = {"alive": True, "packet_loss": 2.5, "rtt_min": 5.0, "rtt_avg": 8.0, "rtt_max": 15.0, "jitter": 2.0}
        sla = WanMonitorService._classify_sla(probe, baseline_rtt=5.0)
        self.assertEqual(sla["status"], "DEGRADED")
        self.assertTrue(sla["alert"])
        self.assertEqual(sla["badge"], "warning")

    def test_classify_sla_healthy(self):
        probe = {"alive": True, "packet_loss": 0.0, "rtt_min": 1.0, "rtt_avg": 1.8, "rtt_max": 2.5, "jitter": 0.5}
        sla = WanMonitorService._classify_sla(probe, baseline_rtt=5.0)
        self.assertEqual(sla["status"], "HEALTHY")
        self.assertFalse(sla["alert"])
        self.assertEqual(sla["badge"], "success")

    @patch.object(WanMonitorService, '_probe_icmp')
    def test_get_wan_health_aggregation(self, mock_probe):
        mock_probe.return_value = {
            "alive": True, "packet_loss": 0.0, "rtt_min": 1.0, "rtt_avg": 2.0, "rtt_max": 3.0, "jitter": 0.2
        }
        res = WanMonitorService.get_wan_health(force=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["summary"]["total"], len(WanMonitorService.WAN_LINKS))
        self.assertEqual(res["summary"]["healthy"], len(WanMonitorService.WAN_LINKS))
        self.assertEqual(res["summary"]["degraded"], 0)
        self.assertEqual(res["summary"]["down"], 0)
        self.assertEqual(res["summary"]["overall_status"], "HEALTHY")

if __name__ == '__main__':
    unittest.main()
