import time
from typing import Dict, Any, Optional, List, Set
from app.models.change_plan import ChangePlan
from app.models.approval import ApprovalRecord
from app.models.change_window import ChangeWindow
from app.models.constants import Vendor, Platform, OperationType
from app.models.device import DeviceIdentity
from app.drivers.factory import NetworkDriverFactory
from app.drivers.base_driver import NetworkDriver
from app.drivers.errors import ValidationError
from app.services.lock_service import DeviceLockService
from app.services.audit_service import AuditService

from app.drivers.security.readonly_guard import bypass_guard

class ApplyExecutor:
    PRODUCTION_APPLY_ENABLED = False  # Production Kill-Switch

    AUTHORIZED_LAB_DEVICES = [
        {"device_id": "SW-248", "management_ip": "10.11.0.248", "serial": "ABC123", "platform": Platform.MOCK_PLATFORM, "environment": "LAB"},
        {"device_id": "SW-10", "management_ip": "10.100.10.10", "serial": "XYZ123", "platform": Platform.MOCK_PLATFORM, "environment": "LAB"},
        {"device_id": "SW-2", "management_ip": "10.100.1.2", "serial": "XYZ999", "platform": Platform.MOCK_PLATFORM, "environment": "LAB"},
        {"device_id": "SW-HPE-5120-LAB", "management_ip": "172.16.11.50", "serial": "XYZ123_HP_LAB", "platform": Platform.HPE_COMWARE, "environment": "LAB"},
        {"device_id": "SW-HP-V1910-LAB", "management_ip": "172.16.11.52", "serial": "ABC123_HP_V1910", "platform": Platform.HP_PROCURVE, "environment": "LAB"},
        {"device_id": "SW-3COM-2928-LAB", "management_ip": "172.16.11.8", "serial": "ABC123_3COM_2928", "platform": Platform.COMWARE_V5, "environment": "LAB"},
        {"device_id": "SW-ARUBA-2930F-LAB", "management_ip": "172.16.11.41", "serial": "ABC123_ARUBA_2930F", "platform": Platform.ARUBA_AOSS, "environment": "LAB"},
        {"device_id": "SW-ARUBA-90-LAB", "management_ip": "172.16.11.90", "serial": "ABC123_ARUBA_90", "platform": Platform.ARUBA_AOSS, "environment": "LAB"}
    ]

    def __init__(self):
        self.lock_service = DeviceLockService()
        self.audit_service = AuditService()
        self._committed_plan_hashes: Set[str] = set()
        self._consumed_approvals: Set[str] = set()

    @bypass_guard
    def execute_plan(self, plan: ChangePlan, approval: ApprovalRecord, window: ChangeWindow, drivers_map: Optional[Dict[str, NetworkDriver]] = None) -> Dict[str, Any]:
        from app.drivers.security.readonly_guard import ProtectedBaselineGuard
        ProtectedBaselineGuard.set_transaction(f"TX-{plan.id}")
        locks_acquired = []

        if not approval:
            raise ValidationError("O ChangePlan deve ser APROVADO antes de ser aplicado.")

        # Combined Idempotency & Approval consumption check
        if (plan.plan_hash in self._committed_plan_hashes or 
            plan.status == ChangePlan.COMMITTED or 
            approval.approval_id in self._consumed_approvals):
            plan.status = ChangePlan.FAILED
            raise ValidationError("PLAN_ALREADY_APPLIED: Este plano de mudança já foi executado e comprometido. APPROVAL_ALREADY_CONSUMED: Esta aprovacao ja foi consumida.")

        # 2. Plan Modification Check
        if approval.plan_hash != plan.compute_hash():
            plan.status = ChangePlan.FAILED
            raise ValidationError("PLAN_MODIFIED: O hash do plano atual diverge do hash aprovado.")
            
        if approval.is_expired():
            plan.status = ChangePlan.FAILED
            raise ValidationError("APPROVAL_EXPIRED: A aprovacao do plano expirou.")

        # Mark approval as consumed immediately
        self._consumed_approvals.add(approval.approval_id)

        # 0. Allowlist Check & Kill-Switch Validation
        for dev_ip in plan.target_devices:
            # Check if it is an authorized lab device
            lab_match = next((d for d in self.AUTHORIZED_LAB_DEVICES if d["management_ip"] == dev_ip), None)
            
            if not self.PRODUCTION_APPLY_ENABLED:
                if not lab_match or lab_match.get("environment") != "LAB":
                    raise ValidationError(f"PRODUCTION_APPLY_DISABLED: O dispositivo {dev_ip} nao esta na allowlist de LAB autorizada.")

        # Resolve drivers
        drivers = {}
        for dev_ip in plan.target_devices:
            if drivers_map and dev_ip in drivers_map:
                drivers[dev_ip] = drivers_map[dev_ip]
            else:
                vendor = Vendor.MOCK
                platform = Platform.MOCK_PLATFORM
                if dev_ip.startswith("10.200"):
                    vendor = Vendor.HPE
                    platform = Platform.HPE_COMWARE
                elif dev_ip.startswith("10.300"):
                    vendor = Vendor.ARUBA
                    platform = Platform.ARUBA_AOSS
                ident = DeviceIdentity(dev_ip, f"SW-{dev_ip.split('.')[-1]}", vendor=vendor, platform=platform, management_ip=dev_ip)
                drivers[dev_ip] = NetworkDriverFactory.get_driver(ident)

        # Check ChangeWindow and identity for operations
        if window:
            for op in plan.operations:
                sw_ip = op["device"]["management_ip"]
                op_type = op["intent"]
                if not window.is_valid(sw_ip, op_type):
                    plan.status = ChangePlan.FAILED
                    raise ValidationError(f"CHANGE_WINDOW_CLOSED: Operacao {op_type} no dispositivo {sw_ip} fora da janela de manutencao.")

        # 3. Lock acquisition (deterministic alphabetical ordering)
        plan.status = ChangePlan.LOCKING
        sorted_devices = sorted(plan.target_devices)
        locks_acquired = []
        try:
            for dev_ip in sorted_devices:
                driver = drivers[dev_ip]
                lock_ok = self.lock_service.acquire_lock(
                    device_id=driver.identity.device_id,
                    owner_job_id=f"job-{plan.id}",
                    username=plan.created_by
                )
                if not lock_ok:
                    plan.status = ChangePlan.BLOCKED
                    raise ValidationError(f"LOCKED: Falha ao adquirir lock do dispositivo {dev_ip}.")
                locks_acquired.append(dev_ip)

            # 4. PreFlight #2 (operational state check after locking)
            plan.status = ChangePlan.PREFLIGHT
            for dev_ip, driver in drivers.items():
                driver.connect()
                try:
                    for op in plan.operations:
                        if op["device"]["management_ip"] == dev_ip and op["intent"] == OperationType.CONFIGURE_ACCESS_PORT.value:
                            port = op["expected_state"]["resource_id"]
                            interface_info = driver.get_interface(port)
                            if interface_info and interface_info.oper_status.upper() == "DOWN":
                                raise ValidationError(f"STATE_CHANGED: Interface {port} do switch {dev_ip} inativa (DOWN) apos lock.")
                finally:
                    driver.disconnect()

            # 5. Apply phase
            plan.status = ChangePlan.APPLYING
            results = []
            applied_ops = []
            start_time = time.time()
            
            for op in plan.operations:
                sw_ip = op["device"]["management_ip"]
                driver = drivers[sw_ip]
                driver.connect()
                try:
                    intent_type = op["intent"]
                    expected = op["expected_state"]
                    
                    if intent_type == OperationType.CREATE_VLAN.value:
                        driver.create_vlan(expected["resource_id"], expected["properties"]["name"], dry_run=False, explicit_apply=True, approved=True)
                    elif intent_type == OperationType.ADD_VLAN_TO_TRUNK.value:
                        driver.add_vlan_to_trunk(expected["resource_id"], op["semantic_operation"]["params"].get("vlan_id", 1008), dry_run=False, explicit_apply=True, approved=True)
                    elif intent_type == OperationType.CONFIGURE_ACCESS_PORT.value:
                        driver.configure_access_port(expected["resource_id"], expected["properties"]["native_vlan"], dry_run=False, explicit_apply=True, approved=True)
                    
                    applied_ops.append(op)
                    results.append({"device": sw_ip, "operation": intent_type, "status": "applied"})
                finally:
                    driver.disconnect()

            # 6. Post-Apply Verification Check
            plan.status = ChangePlan.VALIDATING
            for op in plan.operations:
                sw_ip = op["device"]["management_ip"]
                driver = drivers[sw_ip]
                driver.connect()
                try:
                    if op["intent"] == OperationType.CREATE_VLAN.value:
                        vlan_id = op["expected_state"]["resource_id"]
                        vlan = driver.get_vlan(vlan_id)
                        if not vlan:
                            raise ValidationError(f"VERIFY_FAILED: VLAN {vlan_id} nao encontrada no switch {sw_ip} apos apply.")
                finally:
                    driver.disconnect()

            # Commit
            plan.status = ChangePlan.COMMITTED
            self._committed_plan_hashes.add(plan.plan_hash)
            
            # Log audit
            for op in plan.operations:
                sw_ip = op["device"]["management_ip"]
                self.audit_service.log_change(
                    user=plan.created_by,
                    job_id=f"job-{plan.id}",
                    change_plan_id=plan.id,
                    device_id=op["device"]["device_id"],
                    hostname=op["device"]["hostname"],
                    management_ip=sw_ip,
                    vendor=op["device"]["vendor"],
                    platform=op["device"]["platform"],
                    operation=op["intent"],
                    phase="EXECUTE",
                    commands=op["commands"],
                    before_state=op.get("before_state"),
                    expected_state=op["expected_state"],
                    after_state=op["expected_state"],
                    result="SUCCESS",
                    duration=time.time() - start_time
                )
            return {"status": "success", "plan_id": plan.id}

        except Exception as exec_error:
            # 7. Reverse Rollback
            plan.status = ChangePlan.ROLLING_BACK
            rollback_ok = True
            roll_err = None
            
            try:
                for phase in (plan.rollback_data or {}).get("phases", []):
                    for op in phase["operations"]:
                        sw_ip = op["device"]["management_ip"]
                        if sw_ip in [a["device"]["management_ip"] for a in applied_ops]:
                            driver = drivers[sw_ip]
                            driver.connect()
                            try:
                                intent_type = op["intent"]
                                if intent_type == OperationType.DELETE_VLAN.value:
                                    driver.delete_vlan(op["expected_state"]["resource_id"], dry_run=False, explicit_apply=True, approved=True)
                                elif intent_type == OperationType.REMOVE_VLAN_FROM_TRUNK.value:
                                    driver.remove_vlan_from_trunk(op["expected_state"]["resource_id"], plan.operations[0]["semantic_operation"]["params"].get("vlan_id", 1008), dry_run=False, explicit_apply=True, approved=True)
                                elif intent_type == OperationType.CONFIGURE_ACCESS_PORT.value:
                                    driver.configure_access_port(op["expected_state"]["resource_id"], op["expected_state"]["properties"]["native_vlan"], dry_run=False, explicit_apply=True, approved=True)
                            finally:
                                driver.disconnect()
                
                # Physical Rollback Verification via Discovery
                for op in applied_ops:
                    sw_ip = op["device"]["management_ip"]
                    driver = drivers[sw_ip]
                    driver.connect()
                    try:
                        if op["intent"] == OperationType.CREATE_VLAN.value:
                            vlan_id = op["expected_state"]["resource_id"]
                            vlan = driver.get_vlan(vlan_id)
                            if vlan:
                                raise ValidationError(f"ROLLBACK_VERIFICATION_FAILED: VLAN {vlan_id} ainda persiste no switch {sw_ip} apos rollback.")
                    finally:
                        driver.disconnect()
                        
                plan.status = ChangePlan.ROLLED_BACK
            except Exception as r_err:
                plan.status = "ROLLBACK_FAILED"
                plan.manual_intervention_required = True
                rollback_ok = False
                roll_err = r_err
                
            for ip in locks_acquired:
                driver = drivers[ip]
                self.audit_service.log_change(
                    user=plan.created_by,
                    job_id=f"job-{plan.id}",
                    change_plan_id=plan.id,
                    device_id=driver.identity.device_id,
                    hostname=driver.identity.hostname,
                    management_ip=ip,
                    vendor=driver.identity.vendor,
                    platform=driver.identity.platform,
                    operation="APPLY",
                    phase="ROLLBACK",
                    commands=[],
                    before_state={},
                    expected_state={},
                    after_state={},
                    result="ROLLED_BACK" if rollback_ok else "ROLLBACK_FAILED",
                    error=str(exec_error),
                    rollback_result="SUCCESS" if rollback_ok else f"FAILED: {roll_err}",
                    duration=0.1
                )
            raise exec_error

        finally:
            from app.drivers.security.readonly_guard import ProtectedBaselineGuard
            ProtectedBaselineGuard.set_transaction(None)
            # 8. Unconditional lock release
            for ip in locks_acquired:
                try:
                    self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
                except:
                    pass
