from enum import Enum
import uuid
import time
from typing import Dict, Any, Optional, Union

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ProvisionJob:
    """
    Data class representing an asynchronous Provisioning Job.
    STRICT REQUIREMENT: Absolutely NO clear-text credentials or raw secrets are stored in this model.
    """
    def __init__(
        self,
        job_id: Optional[str] = None,
        plan_id: str = "",
        plan_hash: str = "",
        status: Union[JobStatus, str] = JobStatus.QUEUED,
        created_at: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        worker_id: str = "",
        failure_code: Optional[str] = None,
        error: Optional[str] = None,
        execution_results: Optional[Dict[str, Any]] = None,
        reconciliation: Optional[Dict[str, Any]] = None
    ):
        self.job_id = job_id or f"job_{uuid.uuid4().hex}"
        self.plan_id = plan_id
        self.plan_hash = plan_hash
        self.status = str(status.value if isinstance(status, JobStatus) else status)
        self.created_at = created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.started_at = started_at
        self.finished_at = finished_at
        self.worker_id = worker_id
        self.failure_code = failure_code
        self.error = error
        self.execution_results = execution_results or {}
        self.reconciliation = reconciliation or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert job model to JSON-serializable dictionary."""
        return {
            "job_id": self.job_id,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "worker_id": self.worker_id,
            "failure_code": self.failure_code,
            "error": self.error,
            "execution_results": self.execution_results,
            "reconciliation": self.reconciliation
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProvisionJob':
        """Construct ProvisionJob instance from dictionary."""
        return cls(
            job_id=data.get("job_id"),
            plan_id=data.get("plan_id", ""),
            plan_hash=data.get("plan_hash", ""),
            status=data.get("status", JobStatus.QUEUED),
            created_at=data.get("created_at"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            worker_id=data.get("worker_id", ""),
            failure_code=data.get("failure_code"),
            error=data.get("error"),
            execution_results=data.get("execution_results"),
            reconciliation=data.get("reconciliation")
        )
