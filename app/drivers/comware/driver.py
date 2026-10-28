from typing import List, Dict, Any, Optional
from app.drivers.base_driver import NetworkDriver
from app.models.capabilities import DeviceCapabilities
from app.models.constants import Vendor, Platform, OperationType
from app.models.device import DeviceIdentity
from app.models.interface import NetworkInterface
from app.models.command_plan import CommandPlan, ExpectedState
from app.drivers.errors import ValidationError
from app.drivers.transport.ssh import SSHTransport
from app.drivers.comware.parser import ComwareParser
from app.drivers.comware.command_builder import ComwareCommandBuilder

class ComwareDriver(NetworkDriver):
    def __init__(self, identity: DeviceIdentity, username: Optional[str] = None, password: Optional[str] = None, transport: Optional[SSHTransport] = None):
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
        self.transport = transport
        if self.transport:
            self.transport.platform = Platform.HPE_COMWARE

    def connect(self) -> None:
        if self.transport:
            self.transport.connect()

    def disconnect(self) -> None:
        if self.transport:
            self.transport.disconnect()

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "device_id": self.identity.device_id,
            "hostname": self.identity.hostname,
            "vendor": Vendor.HPE,
            "platform": Platform.HPE_COMWARE
        }

    def get_interfaces(self) -> List[NetworkInterface]:
        if not self.transport:
            return []
        output = self.transport.execute("display current-configuration")
        return ComwareParser.parse_interfaces(output, self.identity.device_id)

    def get_interface(self, name: str) -> Optional[NetworkInterface]:
        return NetworkInterface(self.identity.device_id, name)

    def get_vlans(self) -> List[Dict[str, Any]]:
        if not self.transport:
            return []
        output = self.transport.execute("display vlan brief")
        return ComwareParser.parse_vlans(output)

    def get_vlan(self, vlan_id: int) -> Optional[Dict[str, Any]]:
        vlans = self.get_vlans()
        for v in vlans:
            if v["vlan_id"] == vlan_id:
                return v
        return None

    def get_trunks(self) -> List[Dict[str, Any]]:
        return []

    def get_neighbors(self) -> List[Dict[str, Any]]:
        return []

    def get_stp_state(self) -> Dict[str, Any]:
        return {}

    def get_running_config(self) -> str:
        if not self.transport:
            return ""
        return self.transport.execute("display current-configuration")

    def get_running_config_hash(self) -> str:
        return ComwareParser.compute_config_hash(self.get_running_config())

    def _execute_plan(self, intent: OperationType, commands: List[str], expected_state: ExpectedState, rollback_commands: List[str], dry_run: bool, explicit_apply: bool, approved: bool = False) -> CommandPlan:
        plan = CommandPlan(
            intent=intent,
            device=self.identity,
            commands=commands,
            expected_state=expected_state,
            rollback_commands=rollback_commands
        )
        if dry_run:
            return plan
        if not explicit_apply or not approved:
            raise ValidationError("Aplicacao bloqueada no switch HPE Comware. Requer explicit_apply=True e approved=True.")
        if self.transport:
            for cmd in commands:
                self.transport.execute(cmd)
        return plan

    def create_vlan(self, vlan_id: int, name: Optional[str] = None, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_create_vlan(vlan_id, name)
        rb_cmds = ComwareCommandBuilder.build_delete_vlan(vlan_id)
        expected = ExpectedState("vlan", vlan_id, {"exists": True, "name": name or f"VLAN{vlan_id}"})
        return self._execute_plan(OperationType.CREATE_VLAN, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def delete_vlan(self, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_delete_vlan(vlan_id)
        rb_cmds = ComwareCommandBuilder.build_create_vlan(vlan_id)
        expected = ExpectedState("vlan", vlan_id, {"exists": False})
        return self._execute_plan(OperationType.DELETE_VLAN, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def add_vlan_to_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_add_vlan_to_trunk(port, vlan_id)
        rb_cmds = ComwareCommandBuilder.build_remove_vlan_from_trunk(port, vlan_id)
        expected = ExpectedState("interface", port, {"tagged_vlan_added": vlan_id})
        return self._execute_plan(OperationType.ADD_VLAN_TO_TRUNK, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def remove_vlan_from_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_remove_vlan_from_trunk(port, vlan_id)
        rb_cmds = ComwareCommandBuilder.build_add_vlan_to_trunk(port, vlan_id)
        expected = ExpectedState("interface", port, {"tagged_vlan_removed": vlan_id})
        return self._execute_plan(OperationType.REMOVE_VLAN_FROM_TRUNK, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def configure_access_port(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_configure_access_port(port, vlan_id)
        rb_cmds = ComwareCommandBuilder.build_shutdown_port(port)
        expected = ExpectedState("interface", port, {"mode": "access", "native_vlan": vlan_id})
        return self._execute_plan(OperationType.CONFIGURE_ACCESS_PORT, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def shutdown_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_shutdown_port(port)
        rb_cmds = ComwareCommandBuilder.build_enable_port(port)
        expected = ExpectedState("interface", port, {"admin_status": "down"})
        return self._execute_plan(OperationType.SHUTDOWN_PORT, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def enable_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_enable_port(port)
        rb_cmds = ComwareCommandBuilder.build_shutdown_port(port)
        expected = ExpectedState("interface", port, {"admin_status": "up"})
        return self._execute_plan(OperationType.ENABLE_PORT, cmds, expected, rb_cmds, dry_run, explicit_apply, approved)

    def save_config(self, dry_run: bool = True, explicit_apply: bool = False, approved: bool = False) -> CommandPlan:
        cmds = ComwareCommandBuilder.build_save_config()
        return self._execute_plan(OperationType.SAVE_CONFIG, cmds, None, [], dry_run, explicit_apply, approved)

    def validate_vlan(self, vlan_id: int) -> Dict[str, Any]:
        info = self.get_vlan(vlan_id)
        return {"vlan_id": vlan_id, "aligned": info is not None}

    def validate_trunk(self, port: str) -> Dict[str, Any]:
        return {"port": port, "aligned": True}

    def validate_interface(self, port: str) -> Dict[str, Any]:
        return {"port": port, "aligned": True}

    def validate_configuration(self) -> Dict[str, Any]:
        return {"aligned": True}
