import time
import threading
from typing import Dict, Optional
from app.utils.logging import get_logger

logger = get_logger("lock_service")

class DeviceLock:
    def __init__(self, device_id: str, owner_job_id: str, username: str, ttl: float = 300.0):
        self.device_id = device_id
        self.owner_job_id = owner_job_id
        self.username = username
        self.ttl = ttl
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl
        self.last_heartbeat = self.created_at

    def refresh(self):
        self.last_heartbeat = time.time()
        self.expires_at = self.last_heartbeat + self.ttl

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

class DeviceLockService:
    _instance = None
    _global_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._global_lock:
            if not cls._instance:
                cls._instance = super(DeviceLockService, cls).__new__(cls)
                cls._instance._locks = {}
                cls._instance._heartbeat_threads = {}
            return cls._instance

    def acquire_lock(self, device_id: str, owner_job_id: str, username: str, ttl: float = 300.0) -> bool:
        with self._global_lock:
            current_lock: Optional[DeviceLock] = self._locks.get(device_id)
            now = time.time()
            
            if current_lock and not current_lock.is_expired():
                if current_lock.owner_job_id == owner_job_id:
                    current_lock.refresh()
                    return True
                logger.warning(f"[DEVICE LOCK BLOCKED] Switch {device_id} locked by Job {current_lock.owner_job_id} ({current_lock.username}). Expiracao: {current_lock.expires_at - now:.1f}s")
                return False
                
            # Create or overwrite expired lock
            lock = DeviceLock(device_id, owner_job_id, username, ttl)
            self._locks[device_id] = lock
            logger.info(f"[DEVICE LOCK ACQUIRED] Switch {device_id} locked by Job {owner_job_id} ({username}). TTL: {ttl}s")
            
            # Start heartbeat thread
            self._start_heartbeat(device_id, owner_job_id)
            return True

    def release_lock(self, device_id: str, owner_job_id: str) -> bool:
        with self._global_lock:
            current_lock: Optional[DeviceLock] = self._locks.get(device_id)
            if not current_lock:
                return True
            if current_lock.owner_job_id != owner_job_id:
                logger.warning(f"[DEVICE LOCK RELEASE DENIED] Attempted release of switch {device_id} locked by Job {current_lock.owner_job_id}")
                return False
            self._locks.pop(device_id, None)
            logger.info(f"[DEVICE LOCK RELEASED] Switch {device_id} unlocked.")
            # Heartbeat thread will exit on next iteration
            return True

    def is_locked(self, device_id: str) -> bool:
        with self._global_lock:
            current_lock: Optional[DeviceLock] = self._locks.get(device_id)
            if current_lock and not current_lock.is_expired():
                return True
            return False

    def _start_heartbeat(self, device_id: str, owner_job_id: str):
        def heartbeat_run():
            logger.info(f"[LOCK HEARTBEAT STARTED] Running for device {device_id} | Job {owner_job_id}")
            while True:
                time.sleep(10) # check every 10 seconds, send heartbeat if still active
                with self._global_lock:
                    lock: Optional[DeviceLock] = self._locks.get(device_id)
                    if not lock or lock.owner_job_id != owner_job_id or lock.is_expired():
                        break
                    lock.refresh()
                    logger.debug(f"[LOCK HEARTBEAT RENEWED] Switch {device_id} renewed for Job {owner_job_id}")
            logger.info(f"[LOCK HEARTBEAT STOPPED] Exited for device {device_id} | Job {owner_job_id}")

        t = threading.Thread(target=heartbeat_run, name=f"LockHeartbeat-{device_id}", daemon=True)
        t.start()
