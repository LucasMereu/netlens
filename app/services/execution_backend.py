from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional

class ExecutionBackend(ABC):
    """
    Abstract Execution Backend Interface for NetLens Provisioning Jobs.
    Decouples job submission, status monitoring, and cancellation from concrete task runners.
    """

    @abstractmethod
    def submit(self, job_id: str, fn: Callable, *args, **kwargs) -> str:
        """Submit a job for execution. Returns job_id."""
        pass

    @abstractmethod
    def get_status(self, job_id: str) -> str:
        """Get current status of a submitted job."""
        pass

    @abstractmethod
    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get execution result dictionary for a finished job."""
        pass

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """
        Best-effort attempt to cancel a job.
        QUEUED -> CANCELLED (Returns True)
        RUNNING -> Cannot guarantee immediate cancellation (Returns False)
        """
        pass
