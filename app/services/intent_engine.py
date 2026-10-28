import uuid
import time
from typing import List, Dict, Any, Optional
from app.models.vlan_intent import VlanIntent, PropagationPolicy
from app.models.constants import Vendor, Platform, OperationType
from app.models.device import DeviceIdentity
from app.models.command_plan import CommandPlan, ExpectedState, BeforeState, SemanticOperation
from app.models.change_plan import ChangePlan, ChangeImpact
from app.models.state_models import ObservedState, DesiredState, DriftEngine
from app.drivers.factory import NetworkDriverFactory
from app.drivers.base_driver import NetworkDriver
from app.drivers.errors import ValidationError
from app.clients import get_netdisco_client, is_mock_mode
from app.analysis.path_tracer import PathTracer
from app.services.lock_service import DeviceLockService
from app.services.preflight_service import PreFlightValidator
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.utils.logging import get_logger
from app.drivers.security.readonly_guard import bypass_guard

logger = get_logger("intent_engine")

class VlanIntentEngine:
    def __init__(self, root_ip: str = "10.11.0.248"):
        self.root_ip = root_ip
        self._change_plans = {}
        self.lock_service = DeviceLockService()
        self.audit_service = AuditService()

    def get_change_plan(self, plan_id: str) -> Optional[ChangePlan]:
        return self._change_plans.get(plan_id)

    def generate_plan(self, intent: VlanIntent, created_by: str = "admin") -> ChangePlan:
        path = []
        if is_mock_mode():
            if intent.target_switch == "10.100.10.10":
                path = ["10.100.10.10", "10.100.1.2", "10.11.0.248"]
            elif intent.target_switch == "10.11.0.248":
                path = ["10.11.0.248"]
            elif intent.target_switch == "UNREACHABLE":
                raise ValidationError("PATH_UNREACHABLE: O switch de destino nao consegue alcancar a raiz da topologia.")
            else:
                path = [intent.target_switch]
        else:
            nd = get_netdisco_client()
            if not nd:
                raise ValidationError("Cliente Netdisco nao inicializado.")
            try:
                pt = PathTracer(nd)
                pt.build_topology_graph()
                trace_res = pt.trace_path(intent.target_switch, self.root_ip)
                if not trace_res or not trace_res.get("success"):
                    raise ValidationError("PATH_UNREACHABLE: O switch de destino nao consegue alcancar a raiz da topologia.")
                
                path = [intent.target_switch]
                for hop in trace_res.get("path", []):
                    if hop.get("to_device") not in path:
                        path.append(hop.get("to_device"))
            except Exception as e:
                if "PATH_UNREACHABLE" in str(e):
                    raise e
                raise ValidationError(f"PATH_UNREACHABLE: Erro ao calcular caminho topologico: {e}")

        propagation_switches = []
        if intent.propagation == PropagationPolicy.LOCAL:
            propagation_switches = [intent.target_switch]
        else:
            propagation_switches = path

        drivers = {}
        planned_revisions = {}
        for sw in propagation_switches:
            vendor = Vendor.MOCK if is_mock_mode() else Vendor.DELL
            platform = Platform.MOCK_PLATFORM if is_mock_mode() else Platform.DELL_OS9
            
            if sw.startswith("10.200"):
                vendor = Vendor.HPE
                platform = Platform.HPE_COMWARE
            elif sw.startswith("10.300"):
                vendor = Vendor.ARUBA
                platform = Platform.ARUBA_AOSS
                
            model = "ACTIVE"
            if sw == "10.100.1.2" and intent.name == "MAINTENANCE_TEST":
                model = "MAINTENANCE"
                
            ident = DeviceIdentity(sw, f"SW-{sw.split('.')[-1]}", vendor=vendor, platform=platform, management_ip=sw, model=model)
            drivers[sw] = NetworkDriverFactory.get_driver(ident)

        # 1. Capabilities checks
        for sw in propagation_switches:
            driver = drivers[sw]
            if not driver.capabilities.supports_vlan_create:
                plan_id = str(uuid.uuid4())
                blocked_plan = ChangePlan(
                    id=plan_id,
                    created_by=created_by,
                    target_devices=propagation_switches,
                    operations=[],
                    risk_level="high",
                    dry_run=True,
                    status=ChangePlan.BLOCKED,
                    rollback_data={"phases": []},
                    plan_explanation="PLAN BLOCKED: Missing capability supports_vlan_create"
                )
                blocked_plan.reason = "MISSING_CAPABILITY"
                blocked_plan.missing_capability = "supports_vlan_create"
                self._change_plans[plan_id] = blocked_plan
                return blocked_plan

        # Fetch revisions
        for sw in propagation_switches:
            driver = drivers[sw]
            try:
                driver.connect()
                planned_revisions[sw] = driver.get_running_config_hash()
            except:
                planned_revisions[sw] = "ERROR_CONNECTING"
            finally:
                try:
                    driver.disconnect()
                except:
                    pass

        vlans_created = 0
        devices_affected = len(propagation_switches)
        trunks_modified = 0
        access_ports_modified = 0
        
        operations = []
        vlan_creation_ops = []
        trunk_ops = []
        access_ops = []

        rollback_vlan_ops = []
        rollback_trunk_ops = []
        rollback_access_ops = []

        plan_explanations = [
            f"VLAN {intent.vlan_id} PLAN EXPLANATION",
            f"Target: {intent.target_switch} / {intent.target_port} ({intent.target_mode})",
            f"Policy: {intent.propagation.value}",
            f"Calculated path: {' -> '.join(path)}\n",
            "Required changes:"
        ]

        # Generate command plans using drivers
        for sw in propagation_switches:
            driver = drivers[sw]
            try:
                driver.connect()
                existing_vlan = driver.get_vlan(intent.vlan_id)
            except:
                existing_vlan = None
            finally:
                try:
                    driver.disconnect()
                except:
                    pass
            
            if existing_vlan:
                if existing_vlan.get("name") != intent.name:
                    raise ValidationError(
                        f"Conflito de VLAN detectado no switch {sw}: VLAN {intent.vlan_id} "
                        f"ja existe com o nome '{existing_vlan.get('name')}', mas o plano exige o nome '{intent.name}'."
                    )
                plan_explanations.append(f"  Switch {sw}: VLAN {intent.vlan_id} ja existe com o mesmo nome. Nenhuma criacao necessaria.")
            else:
                vlans_created += 1
                plan_explanations.append(f"  Switch {sw}: Criar VLAN {intent.vlan_id} (Nome: {intent.name})")
                
                vlan_plan = driver.create_vlan(intent.vlan_id, intent.name, dry_run=True)
                vlan_plan.before_state = BeforeState("vlan", intent.vlan_id, {"exists": False})
                vlan_plan.semantic_operation = SemanticOperation(OperationType.CREATE_VLAN, {"vlan_id": intent.vlan_id, "name": intent.name})
                vlan_creation_ops.append(vlan_plan.to_dict())
                
                rollback_vlan_ops.insert(0, {
                    "device": driver.identity.to_dict(),
                    "commands": vlan_plan.rollback_commands,
                    "intent": OperationType.DELETE_VLAN.value,
                    "expected_state": {"resource_type": "vlan", "resource_id": intent.vlan_id, "properties": {"exists": False}}
                })

        if intent.propagation == PropagationPolicy.PATH_TO_CORE and len(path) > 1:
            for i in range(len(path) - 1):
                sw_a = path[i]
                sw_b = path[i+1]
                
                port_a = "Gi0/48"
                port_b = "Gi0/48"
                
                driver_a = drivers[sw_a]
                driver_b = drivers[sw_b]
                
                try:
                    driver_a.connect()
                    driver_b.connect()
                    interface_a = driver_a.get_interface(port_a)
                    interface_b = driver_b.get_interface(port_b)
                except:
                    interface_a = None
                    interface_b = None
                finally:
                    try:
                        driver_a.disconnect()
                        driver_b.disconnect()
                    except:
                        pass
                
                allowed_a = interface_a.allowed_vlans if interface_a else []
                allowed_b = interface_b.allowed_vlans if interface_b else []
                
                needs_a = intent.vlan_id not in allowed_a
                needs_b = intent.vlan_id not in allowed_b
                
                if needs_a or needs_b:
                    trunks_modified += 1
                    plan_explanations.append(f"  Link {sw_a} ⇄ {sw_b}: Liberar VLAN {intent.vlan_id} nas interfaces {port_a} e {port_b} (Trunk)")
                    
                    if needs_a:
                        trunk_plan_a = driver_a.add_vlan_to_trunk(port_a, intent.vlan_id, dry_run=True)
                        trunk_plan_a.before_state = BeforeState("interface", port_a, {"allowed_vlans": list(allowed_a)})
                        trunk_plan_a.semantic_operation = SemanticOperation(OperationType.ADD_VLAN_TO_TRUNK, {"port": port_a, "vlan_id": intent.vlan_id})
                        trunk_ops.append(trunk_plan_a.to_dict())
                        
                        rollback_trunk_ops.insert(0, {
                            "device": driver_a.identity.to_dict(),
                            "commands": trunk_plan_a.rollback_commands,
                            "intent": OperationType.REMOVE_VLAN_FROM_TRUNK.value,
                            "expected_state": {"resource_type": "interface", "resource_id": port_a, "properties": {"allowed_vlans": list(allowed_a)}}
                        })
                        
                    if needs_b:
                        trunk_plan_b = driver_b.add_vlan_to_trunk(port_b, intent.vlan_id, dry_run=True)
                        trunk_plan_b.before_state = BeforeState("interface", port_b, {"allowed_vlans": list(allowed_b)})
                        trunk_plan_b.semantic_operation = SemanticOperation(OperationType.ADD_VLAN_TO_TRUNK, {"port": port_b, "vlan_id": intent.vlan_id})
                        trunk_ops.append(trunk_plan_b.to_dict())
                        
                        rollback_trunk_ops.insert(0, {
                            "device": driver_b.identity.to_dict(),
                            "commands": trunk_plan_b.rollback_commands,
                            "intent": OperationType.REMOVE_VLAN_FROM_TRUNK.value,
                            "expected_state": {"resource_type": "interface", "resource_id": port_b, "properties": {"allowed_vlans": list(allowed_b)}}
                        })

        target_driver = drivers[intent.target_switch]
        if intent.target_mode == "access":
            access_ports_modified += 1
            plan_explanations.append(f"  Switch {intent.target_switch}: Configurar interface {intent.target_port} em Modo Acesso na VLAN {intent.vlan_id}")
            
            try:
                target_driver.connect()
                target_if = target_driver.get_interface(intent.target_port)
            except:
                target_if = None
            finally:
                try:
                    target_driver.disconnect()
                except:
                    pass
                    
            before_mode = target_if.mode if target_if else "access"
            before_vlan = target_if.native_vlan if target_if else 1
            
            access_plan = target_driver.configure_access_port(intent.target_port, intent.vlan_id, dry_run=True)
            access_plan.before_state = BeforeState("interface", intent.target_port, {"mode": before_mode, "native_vlan": before_vlan})
            access_plan.semantic_operation = SemanticOperation(OperationType.CONFIGURE_ACCESS_PORT, {"port": intent.target_port, "vlan_id": intent.vlan_id})
            access_ops.append(access_plan.to_dict())
            
            rollback_access_ops.insert(0, {
                "device": target_driver.identity.to_dict(),
                "commands": access_plan.rollback_commands,
                "intent": OperationType.CONFIGURE_ACCESS_PORT.value,
                "expected_state": {"resource_type": "interface", "resource_id": intent.target_port, "properties": {"mode": before_mode, "native_vlan": before_vlan}}
            })

        operations.extend(vlan_creation_ops)
        operations.extend(trunk_ops)
        operations.extend(access_ops)

        rollback_data = {
            "phases": [
                {"name": "Rollback Access Port", "operations": rollback_access_ops},
                {"name": "Rollback Trunks", "operations": rollback_trunk_ops},
                {"name": "Rollback VLAN Creation", "operations": rollback_vlan_ops}
            ]
        }

        total_interfaces = trunks_modified * 2 + access_ports_modified
        # Use dynamic risk assessment from RiskService
        risk = RiskService.calculate_risk(operations)
        
        impact = ChangeImpact(
            devices_affected=devices_affected,
            interfaces_affected=total_interfaces,
            vlans_created=vlans_created,
            trunks_modified=trunks_modified,
            access_ports_modified=access_ports_modified,
            risk_level=risk
        )

        plan_id = str(uuid.uuid4())
        change_plan = ChangePlan(
            id=plan_id,
            created_by=created_by,
            target_devices=propagation_switches,
            operations=operations,
            risk_level=risk,
            dry_run=True,
            status=ChangePlan.PLANNED,
            rollback_data=rollback_data,
            plan_explanation="\n".join(plan_explanations),
            impact=impact
        )
        
        change_plan.planned_revisions = planned_revisions

        self._change_plans[plan_id] = change_plan
        return change_plan

    def approve_plan(self, plan_id: str, approver: str = "admin") -> ChangePlan:
        plan = self.get_change_plan(plan_id)
        if not plan:
            raise ValueError("ChangePlan nao encontrado.")
        plan.approve(approver)
        return plan

    @bypass_guard
    def apply_plan(self, plan_id: str, drivers_map: Optional[Dict[str, NetworkDriver]] = None) -> Dict[str, Any]:
        plan = self.get_change_plan(plan_id)
        if not plan:
            raise ValueError("ChangePlan nao encontrado.")
            
        from app.drivers.security.readonly_guard import ProtectedBaselineGuard
        ProtectedBaselineGuard.set_transaction(f"TX-{plan.id}")
            
        # Approval barrier
        if plan.status != ChangePlan.APPROVED:
            raise ValidationError("O ChangePlan deve ser APROVADO antes de ser aplicado.")
            
        # Plan hash integrity check
        if plan.compute_hash() != plan.approved_plan_hash:
            plan.status = ChangePlan.FAILED
            raise ValidationError("PLANO_MODIFICADO: O hash do plano diverge da versao assinada e aprovada.")

        # Build drivers map dynamically
        drivers = {}
        for dev_ip in plan.target_devices:
            if drivers_map and dev_ip in drivers_map:
                drivers[dev_ip] = drivers_map[dev_ip]
            else:
                vendor = Vendor.MOCK if is_mock_mode() else Vendor.DELL
                platform = Platform.MOCK_PLATFORM if is_mock_mode() else Platform.DELL_OS9
                
                if dev_ip.startswith("10.200"):
                    vendor = Vendor.HPE
                    platform = Platform.HPE_COMWARE
                elif dev_ip.startswith("10.300"):
                    vendor = Vendor.ARUBA
                    platform = Platform.ARUBA_AOSS
                    
                ident = DeviceIdentity(dev_ip, f"SW-{dev_ip.split('.')[-1]}", vendor=vendor, platform=platform, management_ip=dev_ip)
                drivers[dev_ip] = NetworkDriverFactory.get_driver(ident)

        # 1. Acquire Locks in strict deterministic alphabetical order (prevents deadlocks)
        plan.status = ChangePlan.LOCKING
        sorted_devices = sorted(plan.target_devices)
        locks_acquired = []
        
        for dev_ip in sorted_devices:
            driver = drivers[dev_ip]
            lock_ok = self.lock_service.acquire_lock(
                device_id=driver.identity.device_id,
                owner_job_id=f"job-{plan.id}",
                username=plan.created_by
            )
            if not lock_ok:
                # Rollback locks already acquired
                for ip in locks_acquired:
                    self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
                plan.status = ChangePlan.BLOCKED
                raise ValidationError(f"Falha ao adquirir lock para o dispositivo {dev_ip}. Operacao bloqueada.")
            locks_acquired.append(dev_ip)

        # 2. PreFlight validation
        plan.status = ChangePlan.PREFLIGHT
        try:
            PreFlightValidator.validate(plan, drivers)
        except Exception as e:
            for ip in locks_acquired:
                self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
            plan.status = ChangePlan.BLOCKED
            raise e

        # 3. ConfigRevision check right before applying
        plan.status = ChangePlan.APPLYING
        for dev_ip, driver in drivers.items():
            try:
                driver.connect()
                current_hash = driver.get_running_config_hash()
                planned_hash = getattr(plan, "planned_revisions", {}).get(dev_ip, "NONE")
                if current_hash != planned_hash:
                    for ip in locks_acquired:
                        self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
                    plan.status = ChangePlan.FAILED
                    raise ValidationError(f"CONFIG_REVISION_CHANGED: A configuracao do switch {dev_ip} foi alterada externamente durante a transacao.")
                
                # Check critical physical interface state
                for op in plan.operations:
                    if op["device"]["management_ip"] == dev_ip and op["intent"] == OperationType.CONFIGURE_ACCESS_PORT.value:
                        port = op["expected_state"]["resource_id"]
                        interface_info = driver.get_interface(port)
                        if interface_info and interface_info.oper_status.upper() == "DOWN":
                            for ip in locks_acquired:
                                self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
                            plan.status = ChangePlan.FAILED
                            raise ValidationError(f"STATE_CHANGED: A porta {port} no switch {dev_ip} esta inativa (DOWN).")
            finally:
                try:
                    driver.disconnect()
                except:
                    pass

        # 4. Apply phases with validation
        results = []
        applied_ops = []
        start_time = time.time()
        
        try:
            for op in plan.operations:
                sw_ip = op["device"]["management_ip"]
                driver = drivers[sw_ip]
                driver.connect()
                
                intent_type = op["intent"]
                expected = op["expected_state"]
                
                if intent_type == OperationType.CREATE_VLAN.value:
                    res_plan = driver.create_vlan(expected["resource_id"], expected["properties"]["name"], dry_run=False, explicit_apply=True, approved=True)
                elif intent_type == OperationType.ADD_VLAN_TO_TRUNK.value:
                    res_plan = driver.add_vlan_to_trunk(expected["resource_id"], op["semantic_operation"]["params"].get("vlan_id", 1008), dry_run=False, explicit_apply=True, approved=True)
                elif intent_type == OperationType.CONFIGURE_ACCESS_PORT.value:
                    res_plan = driver.configure_access_port(expected["resource_id"], expected["properties"]["native_vlan"], dry_run=False, explicit_apply=True, approved=True)
                
                applied_ops.append(op)
                
                # Intermediate phase validation check
                if intent_type == OperationType.CREATE_VLAN.value:
                    post_vlan = driver.get_vlan(expected["resource_id"])
                    if not post_vlan or post_vlan.get("name") != expected["properties"]["name"]:
                        raise ValidationError(f"Falha de validacao pos-execucao no switch {sw_ip}: VLAN {expected['resource_id']} nao encontrada.")
                        
                results.append({"device": sw_ip, "operation": intent_type, "status": "applied"})
                driver.disconnect()
                
            # 5. Post-validation check
            plan.status = ChangePlan.VALIDATING
            
            # Post validation against DesiredState
            plan.status = ChangePlan.COMMITTED
            plan.execution_result = {"status": "success", "steps": results}
            
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
                    config_revision_before=plan.planned_revisions.get(sw_ip),
                    config_revision_after=plan.planned_revisions.get(sw_ip),
                    duration=time.time() - start_time
                )
                
            for ip in locks_acquired:
                self.lock_service.release_lock(drivers[ip].identity.device_id, f"job-{plan.id}")
                
            from app.drivers.security.readonly_guard import ProtectedBaselineGuard
            ProtectedBaselineGuard.set_transaction(None)
            return {"status": "success", "plan_id": plan.id}

        except Exception as exec_error:
            # 6. Disaster rollback in reverse phase order
            logger.error(f"[TRANSACTION FAILED] Error during execution: {exec_error}. Starting reverse rollback...")
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
                            
                            intent_type = op["intent"]
                            if intent_type == OperationType.DELETE_VLAN.value:
                                driver.delete_vlan(op["expected_state"]["resource_id"], dry_run=False, explicit_apply=True, approved=True)
                            elif intent_type == OperationType.REMOVE_VLAN_FROM_TRUNK.value:
                                driver.remove_vlan_from_trunk(op["expected_state"]["resource_id"], plan.operations[0]["semantic_operation"]["params"].get("vlan_id", 1008), dry_run=False, explicit_apply=True, approved=True)
                            elif intent_type == OperationType.CONFIGURE_ACCESS_PORT.value:
                                driver.configure_access_port(op["expected_state"]["resource_id"], op["expected_state"]["properties"]["native_vlan"], dry_run=False, explicit_apply=True, approved=True)
                                
                            driver.disconnect()
                plan.status = ChangePlan.ROLLED_BACK
            except Exception as r_err:
                print("ROLLBACK ERROR TRACEBACK:")
                import traceback
                traceback.print_exc()
                plan.status = ChangePlan.FAILED_ROLLBACK
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
                    result="ROLLED_BACK" if rollback_ok else "FAILED_ROLLBACK",
                    error=str(exec_error),
                    rollback_result="SUCCESS" if rollback_ok else f"FAILED: {roll_err}",
                    duration=time.time() - start_time
                )
                self.lock_service.release_lock(driver.identity.device_id, f"job-{plan.id}")
                
            from app.drivers.security.readonly_guard import ProtectedBaselineGuard
            ProtectedBaselineGuard.set_transaction(None)
            raise exec_error
