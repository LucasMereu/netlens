from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class ApprovalRecord:
    # States
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"

    def __init__(self, approval_id: str, plan_id: str, plan_hash: str, device_ids: List[str], requested_by: str, approved_by: Optional[str] = None, reason: Optional[str] = None, ttl_minutes: int = 30):
        self.approval_id = approval_id
        self.plan_id = plan_id
        self.plan_hash = plan_hash
        self.device_ids = device_ids
        self.requested_by = requested_by
        self.approved_by = approved_by
        self.reason = reason
        
        self.requested_at = datetime.utcnow().isoformat() + "Z"
        self.approved_at: Optional[str] = None
        self.expires_at: Optional[str] = None
        self.status = self.DRAFT
        self.ttl_minutes = ttl_minutes

    def approve(self, approved_by: str, reason: str = "Aprovado"):
        self.status = self.APPROVED
        self.approved_by = approved_by
        now = datetime.utcnow()
        self.approved_at = now.isoformat() + "Z"
        self.expires_at = (now + timedelta(minutes=self.ttl_minutes)).isoformat() + "Z"
        self.reason = reason

    def is_expired(self) -> bool:
        if self.status != self.APPROVED:
            return True
        if not self.expires_at:
            return True
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", ""))
            return datetime.utcnow() > exp
        except:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "device_ids": self.device_ids,
            "requested_by": self.requested_by,
            "approved_by": self.approved_by,
            "requested_at": self.requested_at,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "reason": self.reason
        }
