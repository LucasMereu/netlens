from datetime import datetime

class Job:
    # States
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLBACK = "ROLLBACK"

    def __init__(self, id, type, device_id=None, status=PENDING, progress=0, result=None, error=None, rollback_data=None):
        self.id = id
        self.type = type
        self.status = status
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.started_at = None
        self.finished_at = None
        self.device_id = device_id
        self.progress = progress
        self.result = result
        self.error = error
        self.rollback_data = rollback_data

    def start(self):
        self.status = self.RUNNING
        self.started_at = datetime.utcnow().isoformat() + "Z"

    def succeed(self, result=None):
        self.status = self.SUCCESS
        self.progress = 100
        self.result = result
        self.finished_at = datetime.utcnow().isoformat() + "Z"

    def fail(self, error):
        self.status = self.FAILED
        self.error = error
        self.finished_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "device_id": self.device_id,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "rollback_data": self.rollback_data
        }
