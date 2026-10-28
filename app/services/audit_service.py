import os
import json
import time
import re
from typing import Dict, Any, List, Optional

class AuditService:
    def __init__(self, audit_file_path: str = "/Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/audit_log.json"):
        self.audit_file_path = audit_file_path

    def _redact_commands(self, commands: List[str]) -> List[str]:
        redacted = []
        for cmd in commands:
            cmd_sub = re.sub(r'(?i)(password\s+)\S+', r'\1********', cmd)
            cmd_sub = re.sub(r'(?i)(secret\s+)\S+', r'\1********', cmd_sub)
            cmd_sub = re.sub(r'(?i)(community\s+)\S+', r'\1********', cmd_sub)
            cmd_sub = re.sub(r'(?i)(token\s+)\S+', r'\1********', cmd_sub)
            cmd_sub = re.sub(r'(?i)(key\s+)\S+', r'\1********', cmd_sub)
            redacted.append(cmd_sub)
        return redacted

    def log_change(self, user: str, job_id: str, change_plan_id: str, device_id: str, hostname: str, management_ip: str, vendor: str, platform: str, operation: str, phase: str, commands: List[str], before_state: Dict[str, Any], expected_state: Dict[str, Any], after_state: Dict[str, Any], result: str, config_revision_before: Optional[str] = None, config_revision_after: Optional[str] = None, error: Optional[str] = None, rollback_result: Optional[str] = None, duration: float = 0.0):
        
        redacted_cmds = self._redact_commands(commands)
        
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "user": user,
            "job_id": job_id,
            "change_plan_id": change_plan_id,
            "device_id": device_id,
            "hostname": hostname,
            "management_ip": management_ip,
            "vendor": vendor,
            "platform": platform,
            "operation": operation,
            "phase": phase,
            "commands": redacted_cmds,
            "before_state": before_state,
            "expected_state": expected_state,
            "after_state": after_state,
            "result": result,
            "error": error,
            "rollback_result": rollback_result,
            "config_revision_before": config_revision_before,
            "config_revision_after": config_revision_after,
            "duration_seconds": round(duration, 3)
        }
        
        try:
            records = []
            if os.path.exists(self.audit_file_path):
                with open(self.audit_file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        records = json.loads(content)
            records.append(record)
            with open(self.audit_file_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=4)
        except Exception as e:
            print(f"[AUDIT SERVICE ERROR] Falha ao gravar log de auditoria: {e}")
