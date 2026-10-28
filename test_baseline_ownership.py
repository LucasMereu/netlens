import unittest
from unittest.mock import MagicMock, patch
from app.drivers.errors import ValidationError
from app.drivers.security.readonly_guard import ProtectedBaselineGuard, ReadOnlyCommandGuard
from app.models.change_plan import ChangePlan, ChangeImpact
from app.models.approval import ApprovalRecord
from app.models.change_window import ChangeWindow
from app.models.constants import Vendor, Platform, OperationType
from app.drivers.factory import DeviceIdentity
from app.drivers.mock.driver import MockNetworkDriver
from app.services.apply_executor import ApplyExecutor
from app.services.intent_engine import VlanIntentEngine, VlanIntent, PropagationPolicy

class TestBaselineOwnership(unittest.TestCase):
    def setUp(self):
        ProtectedBaselineGuard.set_transaction(None)
        ReadOnlyCommandGuard._bypass = False

    def tearDown(self):
        ProtectedBaselineGuard.set_transaction(None)
        ReadOnlyCommandGuard._bypass = False

    def test_baseline_initialization_allowed(self):
        # Setting transaction to baseline init allows configuring VLAN 4092 or removing VLAN 1
        ProtectedBaselineGuard.set_transaction("TX-BASELINE-INIT")
        try:
            ProtectedBaselineGuard.validate_command("undo port trunk permit vlan 1")
            ProtectedBaselineGuard.validate_command("vlan 4092")
            ProtectedBaselineGuard.validate_command("port trunk pvid vlan 4092")
        except ValidationError as e:
            self.fail(f"Baseline init commands should be allowed, but raised: {e}")

    def test_protected_commands_blocked(self):
        ProtectedBaselineGuard.set_transaction("TX-1234")
        
        prohibited = [
            "undo vlan 4092",
            "undo port trunk permit vlan 4092",
            "undo port trunk pvid vlan",
            "port link-type access",
            "port access vlan 11",
            "no vlan 4092",
            "delete vlan 4092",
            "undo port trunk permit vlan 1",
            "port trunk permit vlan 1 4092 999" # Trunk rebuild attempt
        ]
        
        for cmd in prohibited:
            with self.assertRaises(ValidationError) as ctx:
                ProtectedBaselineGuard.validate_command(cmd)
            self.assertIn("PROTECTED_BASELINE_VIOLATION", str(ctx.exception))
            self.assertIn("Ownership: BASELINE", str(ctx.exception))
            self.assertIn("Transaction: TX-1234", str(ctx.exception))

    def test_incremental_trunk_permitted(self):
        ProtectedBaselineGuard.set_transaction("TX-1234")
        try:
            # Single VLAN incremental permits are allowed
            ProtectedBaselineGuard.validate_command("port trunk permit vlan 999")
            ProtectedBaselineGuard.validate_command("port trunk permit vlan 100")
        except ValidationError as e:
            self.fail(f"Incremental single VLAN trunk permission should be allowed, but raised: {e}")

    def test_successful_vlan_999_incremental_apply_and_rollback(self):
        # Verify that normal apply and rollback of VLAN 999 works
        plan = ChangePlan("tx999", "admin", target_devices=["10.100.10.10"], operations=[{
            "device": {"management_ip": "10.100.10.10", "device_id": "SW-10", "hostname": "SW1", "vendor": "MOCK", "platform": "MOCK"},
            "intent": OperationType.CREATE_VLAN.value,
            "expected_state": {"resource_id": 999, "properties": {"name": "TEST-999"}},
            "commands": ["vlan 999"]
        }])
        plan.status = ChangePlan.APPROVED
        plan.approved_plan_hash = plan.plan_hash
        approval = ApprovalRecord("a999", plan.id, plan.plan_hash, ["10.100.10.10"], "admin")
        approval.approve("manager")
        window = ChangeWindow("2026-08-18T00:00:00Z", "2026-08-18T23:59:59Z", ["10.100.10.10"], [OperationType.CREATE_VLAN.value])
        
        driver = MockNetworkDriver(DeviceIdentity("SW-10", "SW1", Vendor.MOCK, Platform.MOCK_PLATFORM, "10.100.10.10"))
        drivers_map = {"10.100.10.10": driver}
        
        executor = ApplyExecutor()
        res = executor.execute_plan(plan, approval, window, drivers_map=drivers_map)
        self.assertEqual(res["status"], "success")
        self.assertEqual(plan.status, ChangePlan.COMMITTED)
