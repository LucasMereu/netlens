from typing import List, Optional

class ArubaCommandBuilder:
    @staticmethod
    def build_create_vlan(vlan_id: int, name: Optional[str] = None) -> List[str]:
        cmds = ["configure terminal", f"vlan {vlan_id}"]
        if name:
            cmds.append(f"  name \"{name}\"")
        cmds.extend(["exit", "end"])
        return cmds

    @staticmethod
    def build_delete_vlan(vlan_id: int) -> List[str]:
        return ["configure terminal", f"no vlan {vlan_id}", "end"]

    @staticmethod
    def build_add_vlan_to_trunk(port: str, vlan_id: int) -> List[str]:
        return ["configure terminal", f"vlan {vlan_id}", f"  tagged {port}", "exit", "end"]

    @staticmethod
    def build_remove_vlan_from_trunk(port: str, vlan_id: int) -> List[str]:
        return ["configure terminal", f"vlan {vlan_id}", f"  no tagged {port}", "exit", "end"]

    @staticmethod
    def build_configure_access_port(port: str, vlan_id: int) -> List[str]:
        return ["configure terminal", f"vlan {vlan_id}", f"  untagged {port}", "exit", "end"]

    @staticmethod
    def build_shutdown_port(port: str) -> List[str]:
        return ["configure terminal", f"interface {port}", "  disable", "exit", "end"]

    @staticmethod
    def build_enable_port(port: str) -> List[str]:
        return ["configure terminal", f"interface {port}", "  enable", "exit", "end"]

    @staticmethod
    def build_save_config() -> List[str]:
        return ["write memory"]
