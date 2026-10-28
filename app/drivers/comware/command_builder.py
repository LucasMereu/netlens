from typing import List, Optional

class ComwareCommandBuilder:
    @staticmethod
    def build_create_vlan(vlan_id: int, name: Optional[str] = None) -> List[str]:
        cmds = ["system-view", f"vlan {vlan_id}"]
        if name:
            cmds.append(f"  description {name}")
        cmds.extend(["quit", "quit"])
        return cmds

    @staticmethod
    def build_delete_vlan(vlan_id: int) -> List[str]:
        return ["system-view", f"undo vlan {vlan_id}", "quit"]

    @staticmethod
    def build_add_vlan_to_trunk(port: str, vlan_id: int) -> List[str]:
        return ["system-view", f"interface {port}", f"  port trunk permit vlan {vlan_id}", "quit", "quit"]

    @staticmethod
    def build_remove_vlan_from_trunk(port: str, vlan_id: int) -> List[str]:
        return ["system-view", f"interface {port}", f"  undo port trunk permit vlan {vlan_id}", "quit", "quit"]

    @staticmethod
    def build_configure_access_port(port: str, vlan_id: int) -> List[str]:
        return ["system-view", f"interface {port}", "  port link-type access", f"  port access vlan {vlan_id}", "quit", "quit"]

    @staticmethod
    def build_shutdown_port(port: str) -> List[str]:
        return ["system-view", f"interface {port}", "  shutdown", "quit", "quit"]

    @staticmethod
    def build_enable_port(port: str) -> List[str]:
        return ["system-view", f"interface {port}", "  undo shutdown", "quit", "quit"]

    @staticmethod
    def build_save_config() -> List[str]:
        return ["save force"]
