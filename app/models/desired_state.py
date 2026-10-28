from typing import Dict, Any, List

class DesiredState:
    def __init__(self, device_id: str, vlans: Dict[int, Dict[str, Any]] = None, interfaces: Dict[str, Dict[str, Any]] = None):
        self.device_id = device_id
        self.vlans = vlans or {} # {10: {"name": "SERVERS"}}
        self.interfaces = interfaces or {} # {"Gi1/0/48": {"mode": "access", "native_vlan": 10, "allowed_vlans": []}}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "vlans": {str(k): v for k, v in self.vlans.items()},
            "interfaces": self.interfaces
        }
