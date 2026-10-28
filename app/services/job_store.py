import os
import json
import shutil
import fcntl
import uuid
import threading
from typing import Dict, Any, Optional, List
from app.services.config_service import ConfigService
from app.models.provision_job import ProvisionJob, JobStatus
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("job_store")

JOBS_LOCK_FILE = os.path.join(ConfigService.CONFIG_DIR, 'jobs.lock')

class JobProcessFileLock:
    """Process-level file lock using fcntl.flock for multi-worker Gunicorn safety."""
    def __init__(self, lockfile=JOBS_LOCK_FILE):
        self.lockfile = lockfile
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.lockfile, os.O_CREAT | os.O_RDWR)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None

class JobStore:
    """
    Atomic File Persistence & Store for Provisioning Jobs.
    
    STRICT MANDATES:
    1. NEVER stores clear-text credentials or decrypts secrets (No SecretService dependency).
    2. Applies SecretSanitizer.sanitize_dict() before writing to disk.
    3. Multi-worker safe using fcntl.flock(jobs.lock).
    4. Atomic persistence (.tmp + fsync + os.replace + parent directory fsync + .bak recovery).
    """

    JOBS_PATH = os.path.join(ConfigService.CONFIG_DIR, 'jobs.json')

    @classmethod
    def load_jobs(cls, force_reload: bool = True) -> Dict[str, Dict[str, Any]]:
        """Load jobs from disk into memory with atomic backup recovery. Internal helper (no lock)."""
        bak_path = cls.JOBS_PATH + ".bak"

        if os.path.exists(cls.JOBS_PATH):
            try:
                with open(cls.JOBS_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Erro ao carregar jobs.json (arquivo corrompido): {e}")
                if os.path.exists(bak_path):
                    try:
                        logger.warning("Tentando recuperar jobs a partir do backup jobs.json.bak...")
                        with open(bak_path, 'r', encoding='utf-8') as f_bak:
                            return json.load(f_bak)
                    except Exception as e_bak:
                        logger.error(f"Erro ao carregar backup jobs.json.bak: {e_bak}")

        return {}

    @classmethod
    def save_jobs(cls, jobs_data: Dict[str, Dict[str, Any]]) -> None:
        """
        Atomically save jobs to disk:
        .tmp -> flush -> fsync(file) -> os.replace -> fsync(dir) -> .bak
        Applies SecretSanitizer before saving. Internal helper (no lock).
        """
        sanitized_jobs = SecretSanitizer.sanitize_dict(jobs_data)
        tmp_path = cls.JOBS_PATH + ".tmp"
        bak_path = cls.JOBS_PATH + ".bak"

        try:
            # 1. Create backup of current valid file if present
            if os.path.exists(cls.JOBS_PATH) and os.path.getsize(cls.JOBS_PATH) > 0:
                try:
                    shutil.copy2(cls.JOBS_PATH, bak_path)
                except Exception:
                    pass

            # 2. Write to .tmp file, flush, and fsync
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(sanitized_jobs, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())

            # 3. Atomic swap
            os.replace(tmp_path, cls.JOBS_PATH)

            # 4. Fsync parent directory
            try:
                dir_fd = os.open(ConfigService.CONFIG_DIR, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Erro ao salvar de forma atômica o jobs.json: {e}")

    @classmethod
    def get_job(cls, job_id: str) -> Optional[ProvisionJob]:
        """Fetch job by job_id under process lock."""
        with JobProcessFileLock():
            jobs = cls.load_jobs(force_reload=True)
            job_data = jobs.get(job_id)
            if job_data:
                return ProvisionJob.from_dict(job_data)
            return None

    @classmethod
    def save_job(cls, job: ProvisionJob) -> None:
        """Persist or update single job instance under process lock."""
        with JobProcessFileLock():
            jobs = cls.load_jobs(force_reload=True)
            jobs[job.job_id] = job.to_dict()
            cls.save_jobs(jobs)

    @classmethod
    def atomic_transition(cls, job_id: str, expected_statuses: list, new_status: str, updater_fn=None) -> Optional[ProvisionJob]:
        """
        Atomic read-check-modify-write within a single process lock.
        Prevents TOCTOU race conditions on job status transitions.
        
        Args:
            job_id: ID of the job to transition.
            expected_statuses: List of valid current statuses (e.g., [QUEUED]).
            new_status: Target status to set.
            updater_fn: Optional callable(job) to apply additional updates before save.
        
        Returns:
            Updated ProvisionJob if transition succeeded, None if job not found or status mismatch.
        """
        with JobProcessFileLock():
            jobs = cls.load_jobs(force_reload=True)
            job_data = jobs.get(job_id)
            if not job_data:
                return None
            
            current_status = job_data.get("status")
            if current_status not in expected_statuses:
                logger.warning(f"atomic_transition BLOCKED: Job {job_id} status is {current_status}, expected one of {expected_statuses}")
                return None
            
            job = ProvisionJob.from_dict(job_data)
            job.status = new_status
            
            if updater_fn:
                updater_fn(job)
            
            jobs[job.job_id] = job.to_dict()
            cls.save_jobs(jobs)
            return job

    @classmethod
    def create_job_if_not_active(cls, plan_id: str, plan_hash: str) -> ProvisionJob:
        """
        Atomic Double-Apply Check and Job Creation under a single process lock.
        Prevents race conditions and nested locking deadlocks.
        """
        with JobProcessFileLock():
            jobs = cls.load_jobs(force_reload=True)
            for j_data in jobs.values():
                if j_data.get("plan_id") == plan_id and j_data.get("plan_hash") == plan_hash:
                    if j_data.get("status") in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
                        raise ValueError(f"CONCURRENT_EXECUTION_BLOCKED: O plano {plan_id} já possui um Job ativo ({j_data.get('job_id')}) com status {j_data.get('status')}.")

            job_id = f"job_{uuid.uuid4().hex}"
            job = ProvisionJob(
                job_id=job_id,
                plan_id=plan_id,
                plan_hash=plan_hash,
                status=JobStatus.QUEUED
            )
            jobs[job.job_id] = job.to_dict()
            cls.save_jobs(jobs)
            return job

    @classmethod
    def list_all_jobs(cls) -> List[ProvisionJob]:
        """Return list of all stored jobs."""
        with JobProcessFileLock():
            jobs = cls.load_jobs(force_reload=True)
            return [ProvisionJob.from_dict(data) for data in jobs.values()]
