from typing import Dict, List, Set
from app.models.constants import Platform

class CommandPolicy:
    ALLOWLISTS: Dict[Platform, Set[str]] = {
        Platform.DELL_OS9: {
            "show version",
            "show vlan",
            "show interfaces",
            "show lldp neighbors",
            "show spanning-tree",
            "show running-config",
            "show running-config | grep default",
            "show running-config | grep -B 1 \"Port-channel 49\""
        },
        Platform.HPE_COMWARE: {
            "display version",
            "display vlan",
            "display vlan brief",
            "display interface",
            "display lldp neighbor",
            "display stp",
            "display current-configuration"
        },
        Platform.ARUBA_AOSS: {
            "show version",
            "show vlan",
            "show interfaces",
            "show lldp info remote-device",
            "show spanning-tree",
            "show running-config"
        },
        Platform.MOCK_PLATFORM: {
            "show version",
            "show vlan",
            "show interfaces",
            "show lldp neighbors",
            "show spanning-tree",
            "show running-config"
        },
        Platform.HP_PROCURVE: {
            "show version",
            "show vlan",
            "show interfaces",
            "show lldp info remote-device"
        },
        Platform.COMWARE_V5: {
            "display version",
            "display vlan",
            "display interface brief",
            "display lldp neighbor-information"
        },
        Platform.STANTON_OS: {
            "show status"
        }
    }

    @staticmethod
    def is_allowed(platform: Platform, command: str) -> bool:
        cmd_clean = command.strip().lower()
        
        # Explicitly reject configuration modes and mutations
        prohibited_prefixes = ["configure", "system-view", "conf t", "interface ", "vlan ", "write ", "copy ", "save", "reload", "delete ", "erase "]
        for p in prohibited_prefixes:
            if cmd_clean.startswith(p):
                return False
                
        allowed_cmds = CommandPolicy.ALLOWLISTS.get(platform, set())
        
        # Standard strict validation (case-insensitive check)
        if cmd_clean in [c.lower() for c in allowed_cmds]:
            return True
            
        # Prefix matching for interfaces detail checks
        for allowed in allowed_cmds:
            if cmd_clean.startswith(allowed.lower()):
                return True
                
        return False
