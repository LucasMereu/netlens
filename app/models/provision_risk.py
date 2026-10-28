from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

class RiskLevel(str, Enum):
    LOW = "LOW"            # Score 0-25: Standard provision/reuse
    MEDIUM = "MEDIUM"      # Score 26-55: Router/Firewall profile or minor drift
    HIGH = "HIGH"          # Score 56-80: Weak SNMP community warning
    CRITICAL = "CRITICAL"  # Score 81-100: IP collision, API unreachable, or unsafe mutation. BLOCKS APPLY

@dataclass
class RiskAssessment:
    risk_level: RiskLevel
    risk_score: int
    risk_factors: List[str] = field(default_factory=list)
    requires_elevated_approval: bool = False
    can_apply: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "requires_elevated_approval": self.requires_elevated_approval,
            "can_apply": self.can_apply
        }

@dataclass
class ApprovalRecord:
    plan_id: str
    approved_by: str
    approved_at: str
    plan_hash: str
    risk_level: str
    risk_score: int
    tamper_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "plan_hash": self.plan_hash,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "tamper_detected": self.tamper_detected
        }
