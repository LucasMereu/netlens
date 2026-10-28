import re
import hashlib
from typing import List, Dict, Any, Optional
from app.models.interface import NetworkInterface

class DellParser:
    @staticmethod
    def parse_default_vlan(running_config: str) -> int:
        default_vlan = 1
        match = re.search(r"default vlan-id\s+(\d+)", running_config)
        if match:
            default_vlan = int(match.group(1))
        return default_vlan

    @staticmethod
    def parse_port_channel_pvid(running_config: str, channel_num: int = 49) -> int:
        lines = running_config.splitlines()
        pvid = None
        for i, line in enumerate(lines):
            if line.strip().startswith("!"):
                continue
            if "untagged" in line and f"Port-channel {channel_num}" in line:
                j = i - 1
                while j >= 0:
                    prev_line = lines[j].strip()
                    if prev_line.startswith("!"):
                        j -= 1
                        continue
                    if "interface Vlan" in prev_line:
                        vlan_match = re.search(r"interface Vlan\s+(\d+)", prev_line)
                        if vlan_match:
                            pvid = int(vlan_match.group(1))
                            break
                    j -= 1
                if pvid is not None:
                    break
        return pvid

    @staticmethod
    def parse_vlan_output(show_vlan_output: str) -> List[Dict[str, Any]]:
        vlans = []
        lines = show_vlan_output.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("NUM") or line_str.startswith("----") or line_str.startswith("*"):
                continue
            match = re.match(r"^(\d+)\s+(Active|Inactive)\s*(\S+)?", line_str)
            if match:
                vlan_id = int(match.group(1))
                name = match.group(3) or f"VLAN{vlan_id}"
                vlans.append({"vlan_id": vlan_id, "name": name})
        return vlans

    @staticmethod
    def parse_interfaces_output(show_interfaces_output: str, device_id: str = "device") -> List[NetworkInterface]:
        interfaces = []
        matches = re.finditer(r"(?i)^interface\s+(\S+(?:\s+\S+)?)", show_interfaces_output, re.MULTILINE)
        for m in matches:
            if_name = m.group(1)
            interfaces.append(NetworkInterface(
                device_id=device_id,
                name=if_name,
                admin_status="up",
                oper_status="up"
            ))
        return interfaces

    @staticmethod
    def compute_config_hash(running_config: str) -> str:
        # Conservative normalization:
        # 1. CRLF -> LF
        # 2. Strip ending spaces from lines
        # 3. Remove comments/dynamic dates
        # 4. Remove empty lines
        # 5. Guarantee final newline
        lines = []
        for line in running_config.splitlines():
            line_normalized = line.replace('\r\n', '\n').rstrip()
            if not line_normalized or line_normalized.startswith("!") or "Last configuration change" in line_normalized or "Time" in line_normalized or "date" in line_normalized:
                continue
            lines.append(line_normalized)
        
        normalized_config = "\n".join(lines)
        if not normalized_config.endswith("\n"):
            normalized_config += "\n"
            
        return hashlib.sha256(normalized_config.encode('utf-8')).hexdigest()
