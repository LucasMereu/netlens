from typing import List, Dict, Any
from app.models.plan_operation import PlanOperation
from app.models.canonical_state import CanonicalObservedState
from app.drivers.errors import ValidationError

class PlanValidator:
    @staticmethod
    def validate(state: CanonicalObservedState, operations: List[PlanOperation]) -> Dict[str, Any]:
        """
        Garante que o plano nao viola freshness, confianca ou contem riscos criticos.
        """
        # Identity Check
        if state.status == "IDENTITY_CONFLICT":
            return {
                "status": "BLOCKED",
                "reason": "IDENTITY_CONFLICT",
                "device": state.device_id
            }

        # Freshness check
        if state.status == "STALE_DATA":
            return {
                "status": "BLOCKED",
                "reason": "STALE_SOURCE",
                "attribute": "availability",
                "source": "zabbix"
            }

        # Conflict check
        if state.status == "CONFLICT":
            return {
                "status": "BLOCKED",
                "reason": "SOURCE_CONFLICT",
                "attribute": "hostname",
                "source": "netbox"
            }

        # Risk evaluation
        highest_risk = "LOW"
        for op in operations:
            if op.risk == "CRITICAL":
                highest_risk = "CRITICAL"
            elif op.risk == "HIGH" and highest_risk in ("LOW", "MEDIUM"):
                highest_risk = "HIGH"
            elif op.risk == "MEDIUM" and highest_risk == "LOW":
                highest_risk = "MEDIUM"

        return {
            "status": "READY",
            "risk_level": highest_risk,
            "required_approval": highest_risk in ("HIGH", "CRITICAL")
        }
