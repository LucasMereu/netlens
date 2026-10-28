import unittest
from unittest.mock import patch, MagicMock

from app.models.provision_risk import RiskLevel, RiskAssessment
from app.models.provision_policy import PolicyValidationResult, PolicyWarning
from app.models.provision_dependency import DependencyStatus, DependencyResult
from app.services.provision_risk_engine import ProvisionRiskEngine
from app.services.provision_orchestrator import ProvisionOrchestrator, _PLAN_STORE

class TestProvisionRiskEngine(unittest.TestCase):

    def setUp(self):
        _PLAN_STORE.clear()
        self.mock_config = {
            "netbox": {"url": "https://192.168.10.235", "api_token": "mock_token"},
            "zabbix": {"url": "http://192.168.10.108", "user": "Admin", "password": "mock_password"},
            "librenms": {"url": "http://192.168.10.50:8000", "api_token": "mock_token"},
            "netdisco": {"url": "http://192.168.10.51:5000"}
        }

    def test_risk_assessment_low_risk(self):
        policy_result = PolicyValidationResult(passed=True)
        discovery_results = {
            "netbox": DependencyResult(system="NetBox", object_type="device", requested_identifier="sw-hpe-01", status=DependencyStatus.ABSENT),
            "zabbix": DependencyResult(system="Zabbix", object_type="host", requested_identifier="sw-hpe-01", status=DependencyStatus.ABSENT)
        }
        assessment = ProvisionRiskEngine.assess_risk({"hostname": "sw-hpe-01"}, "NETWORK_SWITCH", policy_result, discovery_results)
        self.assertEqual(assessment.risk_level, RiskLevel.LOW)
        self.assertTrue(assessment.can_apply)
        self.assertTrue(assessment.risk_score <= 25)

    def test_risk_assessment_medium_risk_router_profile(self):
        policy_result = PolicyValidationResult(passed=True)
        discovery_results = {
            "netbox": DependencyResult(system="NetBox", object_type="device", requested_identifier="rt-cisco-01", status=DependencyStatus.ABSENT)
        }
        assessment = ProvisionRiskEngine.assess_risk({"hostname": "rt-cisco-01"}, "ROUTER_CISCO", policy_result, discovery_results)
        self.assertEqual(assessment.risk_level, RiskLevel.MEDIUM)
        self.assertTrue(assessment.can_apply)

    def test_risk_assessment_high_risk_snmp_public(self):
        policy_result = PolicyValidationResult(
            passed=True,
            warnings=[PolicyWarning(policy_name="SecurityPolicy", rule="WEAK_SNMP_COMMUNITY", message="Comunidade fraca")]
        )
        discovery_results = {
            "netbox": DependencyResult(system="NetBox", object_type="device", requested_identifier="sw-hpe-01", status=DependencyStatus.ABSENT)
        }
        assessment = ProvisionRiskEngine.assess_risk({"hostname": "sw-hpe-01"}, "NETWORK_SWITCH", policy_result, discovery_results)
        self.assertEqual(assessment.risk_level, RiskLevel.HIGH)
        self.assertTrue(assessment.requires_elevated_approval)

    def test_risk_assessment_critical_risk_blocks_apply(self):
        policy_result = PolicyValidationResult(passed=True)
        discovery_results = {
            "zabbix": DependencyResult(system="Zabbix", object_type="host", requested_identifier="sw-hpe-01", status=DependencyStatus.CONFLICT, conflicts=["IP colidindo"])
        }
        assessment = ProvisionRiskEngine.assess_risk({"hostname": "sw-hpe-01"}, "NETWORK_SWITCH", policy_result, discovery_results)
        self.assertEqual(assessment.risk_level, RiskLevel.CRITICAL)
        self.assertFalse(assessment.can_apply)

    @patch("requests.post")
    @patch("requests.get")
    def test_tamper_detection_invalid_hash(self, mock_get, mock_post):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"results": [], "count": 0}
        mock_get.return_value = mock_res

        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"result": "mock_token"}
        mock_post.return_value = mock_post_res

        input_data = {
            "hostname": "sw-hpe-lab01",
            "ip": "10.11.0.250",
            "site": "RedeTV HQ",
            "model": "HPE 1930",
            "profile": "NETWORK_SWITCH"
        }
        plan = ProvisionOrchestrator.generate_plan(input_data, self.mock_config)
        plan_id = plan["plan_id"]

        with self.assertRaises(ValueError) as ctx:
            ProvisionOrchestrator.approve_plan(plan_id, plan_hash="INVALID_TAMPERED_HASH_123")
        self.assertIn("TAMPER_DETECTED", str(ctx.exception))

if __name__ == '__main__':
    unittest.main()
