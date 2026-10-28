import re
import hashlib
from typing import List, Dict, Any
from app.models.interface import NetworkInterface

class ComwareParser:
    @staticmethod
    def parse_vlans(show_vlan_output: str) -> List[Dict[str, Any]]:
        vlans = []
        # Comware display vlan brief:
        # VLAN ID   Type   Description
        # 1         Common  VLAN 0001
        # 1008      Common  RTV-APPLETV
        lines = show_vlan_output.splitlines()
        for line in lines:
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("VLAN") or line_clean.startswith("---"):
                continue
            match = re.match(r"^(\d+)\s+(\S+)\s+(.+)$", line_clean)
            if match:
                vlan_id = int(match.group(1))
                vlans.append({"vlan_id": vlan_id, "name": match.group(3).strip()})
        return vlans

    @staticmethod
    def parse_interfaces(show_interfaces_output: str, device_id: str = "device") -> List[NetworkInterface]:
        interfaces = []
        matches = re.finditer(r"(?i)^interface\s+(\S+)", show_interfaces_output, re.MULTILINE)
        for m in matches:
            interfaces.append(NetworkInterface(
                device_id=device_id,
                name=m.group(1),
                admin_status="up",
                oper_status="up"
            ))
        return interfaces

    @staticmethod
    def compute_config_hash(running_config: str) -> str:
        lines = []
        for line in running_config.splitlines():
            line_normalized = line.replace('\r\n', '\n').rstrip()
            if not line_normalized or line_normalized.startswith("#") or "version" in line_normalized:
                continue
            lines.append(line_normalized)
        normalized = "\n".join(lines)
        if not normalized.endswith("\n"):
            normalized += "\n"
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
