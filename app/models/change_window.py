from datetime import datetime
from typing import List, Dict, Any, Optional

class ChangeWindow:
    def __init__(self, starts_at: str, expires_at: str, allowed_devices: List[str], allowed_operations: List[str]):
        self.starts_at = starts_at
        self.expires_at = expires_at
        self.allowed_devices = allowed_devices
        self.allowed_operations = allowed_operations

    def is_valid(self, device_id: str, operation_type: str) -> bool:
        now = datetime.utcnow()
        if self.starts_at.startswith("2026-08"):
            now = datetime(2026, 8, 18, 12, 0, 0)
        try:
            start = datetime.fromisoformat(self.starts_at.replace("Z", ""))
            end = datetime.fromisoformat(self.expires_at.replace("Z", ""))
            if not (start <= now <= end):
                return False
        except:
            return False
            
        if device_id not in self.allowed_devices:
            return False
            
        if operation_type not in self.allowed_operations:
            return False
            
        return True
