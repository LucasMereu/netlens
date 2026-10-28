from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.models.capabilities import DeviceCapabilities
from app.models.command_plan import CommandPlan
from app.models.interface import NetworkInterface

class DiscoveryInterface(ABC):
    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_interfaces(self) -> List[NetworkInterface]:
        pass

    @abstractmethod
    def get_interface(self, name: str) -> Optional[NetworkInterface]:
        pass

    @abstractmethod
    def get_vlans(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_vlan(self, vlan_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_trunks(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_neighbors(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_stp_state(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_running_config(self) -> str:
        pass


class ConfigurationInterface(ABC):
    @abstractmethod
    def create_vlan(self, vlan_id: int, name: Optional[str] = None, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def delete_vlan(self, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def add_vlan_to_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def remove_vlan_from_trunk(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def configure_access_port(self, port: str, vlan_id: int, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def shutdown_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def enable_port(self, port: str, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass

    @abstractmethod
    def save_config(self, dry_run: bool = True, explicit_apply: bool = False) -> CommandPlan:
        pass


class ValidationInterface(ABC):
    @abstractmethod
    def validate_vlan(self, vlan_id: int) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_trunk(self, port: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_interface(self, port: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate_configuration(self) -> Dict[str, Any]:
        pass


class NetworkDriver(DiscoveryInterface, ConfigurationInterface, ValidationInterface, ABC):
    def __init__(self, capabilities: DeviceCapabilities):
        self.capabilities = capabilities

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass
