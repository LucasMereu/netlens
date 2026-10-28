from typing import Dict, Any

class SourceOfTruthService:
    # Explicit authority mapping
    AUTHORITY_MATRIX = {
        "hostname": "netbox",
        "management_ip": "netbox",
        "serial": "hardware",
        "manufacturer": "hardware",
        "platform": "hardware",
        "topology": "netdisco",
        "interface_oper_status": "hardware",
        "interface_telemetry": "librenms",
        "availability": "zabbix",
        "vlan_actual": "hardware",
        "vlan_intent": "netbox",
    }

    @staticmethod
    def get_authority(field: str) -> str:
        return SourceOfTruthService.AUTHORITY_MATRIX.get(field, "hardware")
