from typing import Dict, Any, Optional

class ProvisionCapabilityEngine:
    """
    Capability Engine: Resolves model/vendor specific capabilities (SNMP, SSH, CLI, Web-only, LLDP, CDP).
    Interacts with drivers and hardware model matrices.
    """

    @staticmethod
    def get_capabilities(model: str, vendor: Optional[str] = None, profile: Optional[str] = None) -> Dict[str, bool]:
        model_upper = (model or "").upper()
        vendor_upper = (vendor or "").upper()
        profile_upper = (profile or "").upper()

        caps = {
            "snmp": True,
            "ssh": True,
            "vlan_configuration": True,
            "trunk_configuration": True,
            "lldp": True,
            "cdp": False,
            "web_only": False,
            "cli_configuration": True
        }

        # 1. Vendor & Model specific overrides
        if "1930" in model_upper or "OFFICECONNECT" in model_upper:
            # HPE / Aruba 1930 series are Web Managed / Instant On (no full CLI for VLAN config)
            caps["ssh"] = False
            caps["cli_configuration"] = False
            caps["vlan_configuration"] = False
            caps["trunk_configuration"] = False
            caps["web_only"] = True
        elif "3COM" in model_upper or "2928" in model_upper:
            caps["snmp"] = True
            caps["ssh"] = True
            caps["cli_configuration"] = True
            caps["cdp"] = False
        elif "CISCO" in model_upper or "CATALYST" in model_upper:
            caps["cdp"] = True
            caps["lldp"] = True
        elif "SOPHOS" in model_upper or "XGS" in model_upper:
            caps["vlan_configuration"] = False
            caps["trunk_configuration"] = False
            caps["cli_configuration"] = False

        # 2. Profile specific baseline overrides
        if profile_upper in ("SERVER_LINUX", "VM_PROXMOX"):
            caps["vlan_configuration"] = False
            caps["trunk_configuration"] = False
            caps["lldp"] = False
            caps["cdp"] = False
            caps["cli_configuration"] = False

        return caps
