from datetime import datetime
from typing import Dict, Any, List, Optional

class CanonicalProperty:
    def __init__(self, value: Any, source: str, observed_at: str, confidence: str):
        self.value = value
        self.source = source
        self.observed_at = observed_at
        self.confidence = confidence  # AUTHORITATIVE, CORROBORATING, CONFLICTING, OBSERVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "observed_at": self.observed_at,
            "confidence": self.confidence
        }

class CanonicalObservedState:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.hostname: Optional[CanonicalProperty] = None
        self.management_ip: Optional[CanonicalProperty] = None
        self.serial: Optional[CanonicalProperty] = None
        self.manufacturer: Optional[CanonicalProperty] = None
        self.platform: Optional[CanonicalProperty] = None
        
        # Lists of canonical objects or mappings
        self.interfaces: List[Dict[str, Any]] = []
        self.neighbors: List[Dict[str, Any]] = []
        self.vlans: List[Dict[str, Any]] = []
        self.availability: Optional[CanonicalProperty] = None
        
        self.status = "UNKNOWN"  # CONSISTENT, DRIFT, CONFLICT, UNKNOWN, STALE, UNREACHABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "status": self.status,
            "hostname": self.hostname.to_dict() if self.hostname else None,
            "management_ip": self.management_ip.to_dict() if self.management_ip else None,
            "serial": self.serial.to_dict() if self.serial else None,
            "manufacturer": self.manufacturer.to_dict() if self.manufacturer else None,
            "platform": self.platform.to_dict() if self.platform else None,
            "interfaces": self.interfaces,
            "neighbors": self.neighbors,
            "vlans": self.vlans,
            "availability": self.availability.to_dict() if self.availability else None
        }
