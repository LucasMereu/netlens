import unittest
from app.models.provision_reconciliation import (
    ReconciliationState, DesiredState, ObservedState
)
from app.services.provision_reconciliation import ProvisionReconciliationEngine

class TestProvisionReconciliationEngine(unittest.TestCase):

    def setUp(self):
        self.desired = DesiredState(
            hostname="sw-core-01",
            ip="10.11.0.250",
            site="RedeTV HQ",
            model="HPE OfficeConnect 1930",
            profile="NETWORK_SWITCH",
            netbox_role="switch",
            zabbix_groups=["Templates/Network Devices"],
            zabbix_templates=["Template Module Generic SNMP"],
            librenms_protocol="snmp"
        )

    def test_reconciliation_compliant_drift_zero(self):
        observed = ObservedState(
            netbox_status="PRESENT",
            netbox_site="RedeTV HQ",
            netbox_role="switch",
            netbox_ip="10.11.0.250",
            zabbix_status="PRESENT",
            zabbix_groups=["Templates/Network Devices"],
            zabbix_templates=["Template Module Generic SNMP"],
            librenms_status="PRESENT",
            netdisco_status="PRESENT"
        )

        card = ProvisionReconciliationEngine.compare_desired_vs_observed("PROV-2026-TEST01", self.desired, observed)
        self.assertEqual(card.state, ReconciliationState.COMPLIANT)
        self.assertEqual(card.drift_count, 0)
        self.assertEqual(card.system_summaries["netbox"], "PASS")

    def test_reconciliation_template_drift_detection(self):
        # Observed Zabbix has a different template (Cisco IOS instead of Generic SNMP)
        observed = ObservedState(
            netbox_status="PRESENT",
            zabbix_status="PRESENT",
            zabbix_templates=["Cisco IOS"],
            librenms_status="PRESENT",
            netdisco_status="PRESENT"
        )

        card = ProvisionReconciliationEngine.compare_desired_vs_observed("PROV-2026-TEST02", self.desired, observed)
        self.assertEqual(card.state, ReconciliationState.DRIFT)
        self.assertEqual(card.drift_count, 1)
        self.assertEqual(card.drifts[0].classification, "CONFIGURATION_DRIFT")
        self.assertEqual(card.drifts[0].expected, "Template Module Generic SNMP")
        self.assertEqual(card.drifts[0].actual, "Cisco IOS")

    def test_reconciliation_orphan_detection(self):
        # Host present in Zabbix but ABSENT in NetBox -> ORPHAN
        observed = ObservedState(
            netbox_status="ABSENT",
            zabbix_status="PRESENT",
            zabbix_templates=["Template Module Generic SNMP"],
            librenms_status="PRESENT",
            netdisco_status="PRESENT"
        )

        card = ProvisionReconciliationEngine.compare_desired_vs_observed("PROV-2026-TEST03", self.desired, observed)
        self.assertEqual(card.state, ReconciliationState.ORPHAN)
        self.assertTrue(any(d.classification == "ORPHAN_HOST" for d in card.drifts))

    def test_reconciliation_stale_detection(self):
        # NetDisco discovery status is STALE
        observed = ObservedState(
            netbox_status="PRESENT",
            zabbix_status="PRESENT",
            zabbix_templates=["Template Module Generic SNMP"],
            librenms_status="PRESENT",
            netdisco_status="STALE"
        )

        card = ProvisionReconciliationEngine.compare_desired_vs_observed("PROV-2026-TEST04", self.desired, observed)
        self.assertEqual(card.state, ReconciliationState.STALE)
        self.assertTrue(any(d.classification == "STALE_TOPOLOGY" for d in card.drifts))

if __name__ == '__main__':
    unittest.main()
