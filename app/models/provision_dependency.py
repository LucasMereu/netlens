from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

class DependencyStatus(str, Enum):
    ABSENT = "ABSENT"        # Object does not exist. Action: CREATE
    EXISTING = "EXISTING"    # Object exists and matches intent. Action: REUSE
    REUSABLE = "REUSABLE"    # Object exists and can be reused. Action: REUSE
    CONFLICT = "CONFLICT"    # Object identifier collision with incompatible attributes. Action: BLOCK
    UNKNOWN = "UNKNOWN"      # State cannot be determined safely. Action: BLOCK
    STALE = "STALE"          # Data unverified or outdated. Action: BLOCK

@dataclass
class CanonicalHostIdentity:
    hostname: str
    ip: str
    profile: str
    site: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hostname": self.hostname,
            "ip": self.ip,
            "profile": self.profile,
            "site": self.site
        }

@dataclass
class DependencyResult:
    system: str
    object_type: str
    requested_identifier: str
    status: DependencyStatus
    object_id: Optional[Any] = None
    existing_details: Optional[Dict[str, Any]] = None
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "object_type": self.object_type,
            "requested_identifier": self.requested_identifier,
            "status": self.status.value if isinstance(self.status, DependencyStatus) else str(self.status),
            "object_id": self.object_id,
            "existing_details": self.existing_details,
            "conflicts": self.conflicts,
            "warnings": self.warnings
        }
