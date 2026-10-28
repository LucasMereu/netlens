import hashlib
import json
from typing import List, Dict, Any, Optional

class PlanOperation:
    def __init__(self, device_id: str, operation_type: str, interface: Optional[str] = None, old_value: Any = None, new_value: Any = None, risk: str = "LOW"):
        self.device_id = device_id
        self.operation_type = operation_type
        self.interface = interface or ""
        self.old_value = old_value
        self.new_value = new_value
        self.risk = risk
        if self.operation_type == "SET_ACCESS_VLAN" and risk == "LOW":
            self.risk = "HIGH"
        self.dependencies: List[str] = []
        
        self.operation_id = self.compute_id()

    def compute_id(self) -> str:
        norm_params = json.dumps({"old": self.old_value, "new": self.new_value}, sort_keys=True, separators=(",", ":"))
        raw = f"{self.device_id}:{self.operation_type}:{self.interface}:{norm_params}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "device_id": self.device_id,
            "operation_type": self.operation_type,
            "interface": self.interface,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "risk": self.risk,
            "dependencies": self.dependencies
        }
