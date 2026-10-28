import hashlib
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class ChangeImpact:
    def __init__(self, devices_affected: int = 0, interfaces_affected: int = 0, vlans_created: int = 0, trunks_modified: int = 0, access_ports_modified: int = 0, risk_level: str = "low"):
        self.devices_affected = devices_affected
        self.interfaces_affected = interfaces_affected
        self.vlans_created = vlans_created
        self.trunks_modified = trunks_modified
        self.access_ports_modified = access_ports_modified
        self.risk_level = risk_level

    def to_dict(self):
        return {
            "devices_affected": self.devices_affected,
            "interfaces_affected": self.interfaces_affected,
            "vlans_created": self.vlans_created,
            "trunks_modified": self.trunks_modified,
            "access_ports_modified": self.access_ports_modified,
            "risk_level": self.risk_level
        }

class ChangePlan:
    # Expanded transactional States
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    LOCKING = "LOCKING"
    PREFLIGHT = "PREFLIGHT"
    APPLYING = "APPLYING"
    VALIDATING = "VALIDATING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED_ROLLBACK = "FAILED_ROLLBACK"

    def __init__(self, id: str, created_by: str, target_devices: Optional[List[str]] = None, operations: Optional[List[Dict[str, Any]]] = None, risk_level: str = "low", dry_run: bool = True, status: str = DRAFT, execution_result: Optional[Dict[str, Any]] = None, rollback_data: Optional[Dict[str, Any]] = None, plan_explanation: Optional[str] = None, impact: Optional[ChangeImpact] = None):
        self.id = id
        self.created_by = created_by
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.target_devices = target_devices or []
        self.operations = operations or []
        self.risk_level = risk_level
        self.dry_run = dry_run
        self.status = status
        self.execution_result = execution_result
        self.rollback_data = rollback_data
        self.plan_explanation = plan_explanation
        self.impact = impact or ChangeImpact()
        
        # Approval tracking
        self.approved_by: Optional[str] = None
        self.approved_at: Optional[str] = None
        self.approval_reason: Optional[str] = None
        
        # Hash computation
        self.plan_hash = self.compute_hash()
        self.approved_plan_hash: Optional[str] = None

    def compute_hash(self) -> str:
        # Compute SHA-256 of operations list to ensure integrity
        ops_str = json.dumps(self.operations, sort_keys=True)
        return hashlib.sha256(ops_str.encode('utf-8')).hexdigest()

    def approve(self, approver: str, reason: str = "Aprovado pelo operador"):
        if self.status not in (self.DRAFT, self.PLANNED, self.PENDING_APPROVAL):
            raise ValueError(f"Nao e possivel aprovar ChangePlan no estado {self.status}")
        self.status = self.APPROVED
        self.approved_by = approver
        self.approved_at = datetime.utcnow().isoformat() + "Z"
        self.approval_reason = reason
        self.approved_plan_hash = self.compute_hash()

    def apply(self):
        if self.status != self.APPROVED:
            raise ValueError("O ChangePlan deve ser APROVADO antes de ser aplicado.")
        self.status = self.APPLYING

    def to_dict(self):
        return {
            "id": self.id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "target_devices": self.target_devices,
            "operations": self.operations,
            "risk_level": self.risk_level,
            "dry_run": self.dry_run,
            "status": self.status,
            "execution_result": self.execution_result,
            "rollback_data": self.rollback_data,
            "plan_explanation": self.plan_explanation,
            "impact": self.impact.to_dict() if self.impact else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "approval_reason": self.approval_reason,
            "plan_hash": self.plan_hash,
            "approved_plan_hash": self.approved_plan_hash
        }
