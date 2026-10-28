import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Callable, Optional
from app.services.execution_backend import ExecutionBackend
from app.utils.logging import get_logger

logger = get_logger("inprocess_backend")

class InProcessExecutionBackend(ExecutionBackend):
    """
    Concrete In-Process Execution Backend using ThreadPoolExecutor.
    Maintains zero external dependencies (No Celery/Redis required).
    """

    def __init__(self, max_workers: int = 5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="netlens_job_worker")
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: str, fn: Callable, *args, **kwargs) -> str:
        """Submit callable function to bounded thread pool."""
        with self._lock:
            future = self.executor.submit(fn, *args, **kwargs)
            self._futures[job_id] = future
            logger.info(f"Job {job_id} submetido com sucesso ao InProcessExecutionBackend.")
            return job_id

    def get_status(self, job_id: str) -> str:
        """Inspect ThreadPool future status."""
        with self._lock:
            future = self._futures.get(job_id)
            if not future:
                return "UNKNOWN"
            if future.running():
                return "RUNNING"
            elif future.done():
                if future.cancelled():
                    return "CANCELLED"
                elif future.exception():
                    return "FAILED"
                return "SUCCEEDED"
            return "QUEUED"

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve result of executed future if completed."""
        with self._lock:
            future = self._futures.get(job_id)
            if not future or not future.done():
                return None
            try:
                return future.result()
            except Exception as e:
                return {"error": str(e)}

    def cancel(self, job_id: str) -> bool:
        """
        Best-effort job cancellation.
        Returns True if cancelled while QUEUED.
        Returns False if already RUNNING or done.
        """
        with self._lock:
            future = self._futures.get(job_id)
            if not future:
                return False
            cancelled = future.cancel()
            if cancelled:
                logger.info(f"Job {job_id} cancelado com sucesso antes do início da execução.")
            else:
                logger.warning(f"Job {job_id} não pode ser cancelado (já em estado RUNNING ou concluído).")
            return cancelled
