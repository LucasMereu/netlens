import time
import uuid
import threading
from typing import Dict, Any, Optional, List
from app.models.provision_job import ProvisionJob, JobStatus
from app.services.job_store import JobStore
from app.services.inprocess_execution_backend import InProcessExecutionBackend
from app.services.provision_orchestrator import ProvisionOrchestrator
from app.services.provision_reconciliation import ProvisionReconciliationEngine
from app.services.config_service import ConfigService
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("job_engine")

class JobEngine:
    """
    Asynchronous Job Orchestrator & Lifecycle Engine for NetLens.
    
    STRICT MANDATES & GUARANTEES:
    1. Decouples HTTP request cycle from long-running provisioning execution.
    2. Enforces double-apply protection via plan_id + plan_hash locking.
    3. Multi-worker safe using fcntl.flock(jobs.lock).
    4. Idempotent crash recovery handling (QUEUED/RUNNING -> FAILED with failure_code).
    5. Zero raw credential storage or secret leaks.
    """

    _backend = None
    _backend_lock = threading.Lock()

    @classmethod
    def _get_backend(cls):
        """Lazy initialization of the execution backend. Safe for WSGI fork()."""
        if cls._backend is None:
            with cls._backend_lock:
                if cls._backend is None:
                    cls._backend = InProcessExecutionBackend(max_workers=5)
        return cls._backend

    @classmethod
    def submit_plan_execution(cls, plan_id: str, config: Dict[str, Any], plan_hash: Optional[str] = None) -> ProvisionJob:
        """
        Quad-validates plan, checks idempotency, creates QUEUED job, and submits to background execution backend.
        Returns created ProvisionJob immediately without blocking HTTP response.
        """
        # 1. Pre-validation of Plan in Orchestrator (read-only verification)
        plan = ProvisionOrchestrator.get_plan(plan_id)
        if not plan:
            raise KeyError(f"Plan {plan_id} não localizado.")

        if plan["status"] in ("EXECUTING", "APPLIED", "COMMITTED"):
            raise ValueError(f"CONCURRENT_EXECUTION_BLOCKED: O plano {plan_id} já está em execução ou foi aplicado (status: {plan['status']}).")

        if plan["status"] != "APPROVED":
            raise ValueError(f"UNAPPROVED_PLAN: O plano {plan_id} precisa ser APROVADO antes da execução (status atual: {plan['status']}).")

        calc_hash = plan.get("hash")
        if plan_hash and calc_hash != plan_hash:
            raise ValueError("TAMPER_DETECTED: O hash informado no Apply não corresponde ao hash do plano aprovado. Aplicação abortada.")

        # 2. Multi-worker Idempotency Check & Atomic Job Creation via JobStore
        job = JobStore.create_job_if_not_active(plan_id, calc_hash)

        # 3. Submit background execution task
        cls._get_backend().submit(job.job_id, cls._run_job_worker, job.job_id, plan_id, config, calc_hash)
        logger.info(f"Job {job.job_id} criado e submetido para execução assíncrona do plano {plan_id}.")
        return job

    @classmethod
    def _run_job_worker(cls, job_id: str, plan_id: str, config: Dict[str, Any], plan_hash: str) -> None:
        """
        Background Worker Thread Execution.
        Updates status to RUNNING, executes ProvisionOrchestrator.apply_plan, and records result.
        """
        worker_id = f"thread_{threading.get_ident()}"

        # 1. Atomic transition QUEUED -> RUNNING (prevents TOCTOU race condition)
        def _set_running(job):
            job.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job.worker_id = worker_id

        job = JobStore.atomic_transition(
            job_id,
            expected_statuses=[JobStatus.QUEUED.value],
            new_status=JobStatus.RUNNING.value,
            updater_fn=_set_running
        )
        if not job:
            logger.warning(f"Job {job_id} foi cancelado, removido ou já transitou antes de iniciar a execução.")
            return

        # 2. Execute Orchestrator apply_plan (WITHOUT holding jobs.lock)
        try:
            execution_res = ProvisionOrchestrator.apply_plan(plan_id, config, plan_hash)
            sanitized_res = SecretSanitizer.sanitize_dict(execution_res.get("results", {}))

            # Perform post-apply reconciliation summary
            reconciliation_report = {}
            try:
                audit_path = ConfigService.CONFIG_DIR + "/audit_log.json"
                plan_data = ProvisionOrchestrator.get_plan(plan_id)
                reconciliation_report = ProvisionReconciliationEngine.verify_and_reconcile(plan_id, plan_data, sanitized_res, audit_path)
                reconciliation_report = SecretSanitizer.sanitize_dict(reconciliation_report)
            except Exception as e_rec:
                logger.warning(f"Erro na reconciliação pós-aplicação do Job {job_id}: {e_rec}")

            # 3. Update status to SUCCEEDED
            job.status = JobStatus.SUCCEEDED.value
            job.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job.execution_results = sanitized_res
            job.reconciliation = reconciliation_report
            JobStore.save_job(job)
            logger.info(f"Job {job_id} concluído com SUCESSO.")

        except Exception as e:
            sanitized_err = SecretSanitizer.sanitize_exception(e)
            logger.error(f"Falha na execução do Job {job_id}: {sanitized_err}")

            job.status = JobStatus.FAILED.value
            job.failure_code = "EXECUTION_ERROR"
            job.error = sanitized_err
            job.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            JobStore.save_job(job)

    @classmethod
    def recover(cls) -> int:
        """
        Idempotent Startup Recovery.
        Scans for orphan QUEUED or RUNNING jobs abandoned during system restart.
        Transitions them to FAILED with failure_code 'EXECUTION_INTERRUPTED_BY_RESTART'.
        Safe for repeated invocations across create_app() calls.
        """
        from app.services.job_store import JobProcessFileLock
        recovered_count = 0
        with JobProcessFileLock():
            jobs = JobStore.load_jobs(force_reload=True)
            modified = False
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            for j_id, j_data in jobs.items():
                status = j_data.get("status")
                if status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
                    j_data["status"] = JobStatus.FAILED.value
                    j_data["failure_code"] = "EXECUTION_INTERRUPTED_BY_RESTART"
                    j_data["error"] = "Execution interrupted by system restart"
                    j_data["finished_at"] = now_iso
                    modified = True
                    recovered_count += 1
                    logger.warning(f"Crash Recovery: Job {j_id} em estado {status} foi marcado como FAILED (EXECUTION_INTERRUPTED_BY_RESTART).")

            if modified:
                JobStore.save_jobs(jobs)

        return recovered_count

    @classmethod
    def get_job(cls, job_id: str) -> Optional[ProvisionJob]:
        """Fetch job model by job_id."""
        return JobStore.get_job(job_id)

    @classmethod
    def get_job_result(cls, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch sanitized job execution result.
        Defense in depth: applies SecretSanitizer.sanitize_dict() on output.
        """
        job = JobStore.get_job(job_id)
        if not job:
            return None

        result_payload = {
            "job_id": job.job_id,
            "plan_id": job.plan_id,
            "plan_hash": job.plan_hash,
            "status": job.status,
            "failure_code": job.failure_code,
            "error": job.error,
            "execution_results": job.execution_results,
            "reconciliation": job.reconciliation
        }
        return SecretSanitizer.sanitize_dict(result_payload)
