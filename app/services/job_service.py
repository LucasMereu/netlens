import uuid
import threading
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from app.models.job import Job
from app.utils.logging import get_logger

logger = get_logger("job_service")

class JobService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(JobService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_workers=5, default_timeout=60):
        if self._initialized:
            return
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="JobWorker")
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self._initialized = True
        logger.info(f"JobService inicializado com {max_workers} workers.")

    def create_job(self, job_type: str, device_id: str = None) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, type=job_type, device_id=device_id)
        with self.jobs_lock:
            self.jobs[job_id] = job
        logger.info(f"[JOB CREATED] Job ID: {job_id} | Type: {job_type} | Device: {device_id}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self.jobs_lock:
            return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Job]:
        with self.jobs_lock:
            return list(self.jobs.values())

    def submit_job(self, job: Job, func, timeout=None, *args, **kwargs):
        timeout = timeout or self.default_timeout
        job.start()
        
        def wrapper():
            logger.info(f"[JOB STARTED] Job ID: {job.id} | Thread: {threading.current_thread().name}")
            try:
                # Execute the function inside the thread
                # The function is expected to open its own connection from connection pool if db access is needed
                future = self.executor.submit(func, *args, **kwargs)
                result = future.result(timeout=timeout)
                job.succeed(result)
                logger.info(f"[JOB SUCCESS] Job ID: {job.id} | Duration: {job.finished_at}")
            except TimeoutError as te:
                logger.error(f"[JOB TIMEOUT] Job ID: {job.id} | Executou por mais de {timeout} segundos.")
                job.fail(f"Job timed out after {timeout} seconds.")
            except Exception as e:
                logger.error(f"[JOB FAILED] Job ID: {job.id} | Error: {e}", exc_info=True)
                job.fail(str(e))

        # Submit wrapper to thread executor so it doesn't block the caller
        threading.Thread(target=wrapper, name=f"JobWrapper-{job.id}", daemon=True).start()
        return job
