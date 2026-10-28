import hashlib
from typing import List, Dict, Any, Optional
from app.drivers.base_driver import NetworkDriver
from app.models.capabilities import DeviceCapabilities
from app.models.constants import Vendor, Platform, OperationType
from app.models.device import DeviceIdentity
from app.models.interface import NetworkInterface
from app.models.command_plan import CommandPlan, ExpectedState
from app.drivers.errors import ValidationError, UnsupportedOperationError
from app.drivers.transport.mock import MockTransport
from app.drivers.dell.parser import DellParser

class MockSwitchState:
    def __init__(self):
        self.vlans = {1: {"name": "default"}}
        self.interfaces = {
            "Gi0/1": {"name": "Gi0/1", "mode": "access", "native_vlan": 1, "allowed_vlans": [], "admin_status": "up", "oper_status": "up"},
            "Gi0/2": {"name": "Gi0/2", "mode": "trunk", "native_vlan": 1, "allowed_vlans": [1, 10, 20], "admin_status": "up", "oper_status": "up"},
            "Gi0/24": {"name": "Gi0/24", "mode": "access", "native_vlan": 1, "allowed_vlans": [], "admin_status": "up", "oper_status": "up"},
            "Gi0/48": {"name": "Gi0/48", "mode": "trunk", "native_vlan": 1, "allowed_vlans": [1, 10, 20], "admin_status": "up", "oper_status": "up"}
        }
        self.running_config = "! Mock Running Config\n"

class MockNetworkDriver(NetworkDriver):
    def __init__(self, identity: DeviceIdentity, transport: Optional[MockTransport] = None):
        caps = DeviceCapabilities(
            supports_vlan_create=True,
            supports_vlan_delete=True,
            supports_access_port=True,
            supports_trunk_port=True,
            supports_trunk_vlan_add=True,
            supports_trunk_vlan_remove=True,
            supports_lldp=True,
            supports_cdp=False,
            supports_stp=True,
            supports_config_save=True,
            supports_config_rollback=False,
            supports_config_revision=True
        )
        super().__init__(caps)
        self.identity = identity
        self.transport = transport or MockTransport(identity.management_ip or "127.0.0.1")
        self.transport.platform = Platform.MOCK_PLATFORM
        self.state = MockSwitchState()
        self.config_revision = "MOCK_REV_ABC123"

    def connect(self) -> None:
        self.transport.connect()

    def disconnect(self) -> None:
        self.transport.disconnect()

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "device_id": self.identity.device_id,
            "hostname": self.identity.hostname,
            "vendor": Vendor.MOCK,
            "platform": Platform.MOCK_PLATFORM
        }

    def get_interfaces(self) -> List[NetworkInterface]:
        interfaces = []
        for name, data in self.state.interfaces.items():
            interfaces.append(NetworkInterface(
                device_id=self.identity.device_id,
                name=name,
                admin_status=data["admin_status"],
                oper_status=data["oper_status"],
                mode=data["mode"],
                native_vlan=data["native_vlan"],
                allowed_vlans=data["allowed_vlans"]
            ))
        return interfaces

    def get_interface(self, name: str) -> Optional[NetworkInterface]:
        data = self.state.interfaces.get(name)
        if not data:
            return None
        return NetworkInterface(
            device_id=self.identity.device_id,
            name=name,
            admin_status=data["admin_status"],
            oper_status=data["oper_status"],
            mode=data["mode"],
            native_vlan=data["native_vlan"],
            allowed_vlans=data["allowed_vlans"]
        )

    def get_vlans(self) -> List[Dict[str, Any]]:
        return [{"vlan_id": v_id, "name": info["name"]} for v_id, info in self.state.vlans.items()]

    def get_vlan(self, vlan_id: int) -> Optional[Dict[str, Any]]:
        info = self.state.vlans.get(vlan_id)
        if not info:
            return None
        return {"vlan_id": vlan_id, "name": info["name"]}

    def get_trunks(self) -> List[Dict[str, Any]]:
        return [self.state.interfaces[name] for name, info in self.state.interfaces.items() if info["mode"] == "trunk"]

    def get_neighbors(self) -> List[Dict[str, Any]]:
        return []

    def get_stp_state(self) -> Dict[str, Any]:
        return {"stp_enabled": True}

    def get_running_config(self) -> str:
        return self.state.running_config

    def get_running_config_hash(self) -> str:
        return self.config_revision

    # Configuration operations with Triple Barrier apply check
    def _process_configuration(self, intent: OperationType, commands: List[str], expected_state: ExpectedState, rollback_commands: List[str], apply_func: Any, dry_run: bool, explicit_apply: bool, approved: bool = False) -> CommandPlan:
        plan = CommandPlan(
            intent=intent,
            device=self.identity,
            commands=commands,
            expected_state=expected_state,
            rollback_commands=rollback_commands
        )
        
        if dry_run:
            return plan
            
        # Triple barrier protection check
        if not explicit_apply or not approved:
            raise ValidationError("Aplicacao de comandos bloqueada. Exige explicit_apply=True e approved=True.")
            
        # Apply simulated changes to internal MockSwitchState
        apply_func()
        
        # Write to transport history
        for cmd in commands:
            self.transport.execute(cmd)
            
        return plan

    def create_vlan(self, vlan_id: int, name: Optional[str] = None, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        vlan_name = name or f"VLAN{vlan_id}"
        cmds = [f"vlan {vlan_id}", f"name {vlan_name}"]
        rb_cmds = [f"no vlan {vlan_id}"]
        expected = ExpectedState("vlan", vlan_id, {"exists": True, "name": vlan_name})
        
        def apply():
            self.state.vlans[vlan_id] = {"name": vlan_name}
            self.state.running_config += f"vlan {vlan_id}\n name {vlan_name}\n"

        return self._process_configuration(OperationType.CREATE_VLAN, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def delete_vlan(self, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"no vlan {vlan_id}"]
        rb_cmds = [f"vlan {vlan_id}"]
        expected = ExpectedState("vlan", vlan_id, {"exists": False})
        
        def apply():
            self.state.vlans.pop(vlan_id, None)

        return self._process_configuration(OperationType.DELETE_VLAN, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def add_vlan_to_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"interface {port}", f"switchport trunk allowed vlan add {vlan_id}"]
        rb_cmds = [f"interface {port}", f"switchport trunk allowed vlan remove {vlan_id}"]
        
        orig_allowed = list(self.state.interfaces.get(port, {}).get("allowed_vlans", []))
        expected = ExpectedState("interface", port, {"allowed_vlans": sorted(list(set(orig_allowed + [vlan_id])))})
        
        def apply():
            if port in self.state.interfaces:
                allowed = self.state.interfaces[port]["allowed_vlans"]
                if vlan_id not in allowed:
                    allowed.append(vlan_id)

        return self._process_configuration(OperationType.ADD_VLAN_TO_TRUNK, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def remove_vlan_from_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"interface {port}", f"switchport trunk allowed vlan remove {vlan_id}"]
        rb_cmds = [f"interface {port}", f"switchport trunk allowed vlan add {vlan_id}"]
        
        orig_allowed = list(self.state.interfaces.get(port, {}).get("allowed_vlans", []))
        new_allowed = [v for v in orig_allowed if v != vlan_id]
        expected = ExpectedState("interface", port, {"allowed_vlans": new_allowed})
        
        def apply():
            if port in self.state.interfaces:
                allowed = self.state.interfaces[port]["allowed_vlans"]
                if vlan_id in allowed:
                    allowed.remove(vlan_id)

        return self._process_configuration(OperationType.REMOVE_VLAN_FROM_TRUNK, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def configure_access_port(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"interface {port}", f"switchport access vlan {vlan_id}"]
        rb_cmds = [f"interface {port}", f"switchport access vlan 1"]
        expected = ExpectedState("interface", port, {"mode": "access", "native_vlan": vlan_id})
        
        def apply():
            if port in self.state.interfaces:
                self.state.interfaces[port]["mode"] = "access"
                self.state.interfaces[port]["native_vlan"] = vlan_id

        return self._process_configuration(OperationType.CONFIGURE_ACCESS_PORT, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def shutdown_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"interface {port}", "shutdown"]
        rb_cmds = [f"interface {port}", "no shutdown"]
        expected = ExpectedState("interface", port, {"admin_status": "down"})
        
        def apply():
            if port in self.state.interfaces:
                self.state.interfaces[port]["admin_status"] = "down"

        return self._process_configuration(OperationType.SHUTDOWN_PORT, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def enable_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = [f"interface {port}", "no shutdown"]
        rb_cmds = [f"interface {port}", "shutdown"]
        expected = ExpectedState("interface", port, {"admin_status": "up"})
        
        def apply():
            if port in self.state.interfaces:
                self.state.interfaces[port]["admin_status"] = "up"

        return self._process_configuration(OperationType.ENABLE_PORT, cmds, expected, rb_cmds, apply, dry_run, explicit_apply, approved)

    def save_config(self, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        return self._process_configuration(OperationType.SAVE_CONFIG, ["write memory"], None, [], lambda: None, dry_run, explicit_apply, approved)

    # Validation Interface
    def validate_vlan(self, vlan_id: int) -> Dict[str, Any]:
        exists = vlan_id in self.state.vlans
        return {"vlan_id": vlan_id, "aligned": exists}

    def validate_trunk(self, port: str) -> Dict[str, Any]:
        return {"port": port, "aligned": True}

    def validate_interface(self, port: str) -> Dict[str, Any]:
        return {"port": port, "aligned": True}

    def validate_configuration(self) -> Dict[str, Any]:
        return {"aligned": True}
