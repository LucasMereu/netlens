from typing import Dict, Any, List, Tuple
from app.models.provision_dependency import DependencyStatus, DependencyResult, CanonicalHostIdentity

class ProvisionIdempotencyEngine:
    """
    Idempotency Engine: Correlates canonical identity across NetBox, Zabbix, LibreNMS, and NetDisco.
    Classifies operations into CREATE, REUSE, or BLOCK.
    """

    @staticmethod
    def classify_and_generate_actions(canonical: CanonicalHostIdentity, discovery_results: Dict[str, DependencyResult]) -> Tuple[bool, Dict[str, str], List[str]]:
        """
        Returns (can_proceed, system_actions, block_reasons).
        system_actions: {"netbox": "CREATE"/"REUSE", "zabbix": "CREATE"/"REUSE", ...}
        """
        can_proceed = True
        system_actions = {}
        block_reasons = []

        for sys_name, res in discovery_results.items():
            if res.status in (DependencyStatus.CONFLICT, DependencyStatus.UNKNOWN, DependencyStatus.STALE):
                can_proceed = False
                system_actions[sys_name] = "BLOCK"
                for conflict in res.conflicts:
                    block_reasons.append(f"[{sys_name.upper()}] {conflict}")
                if not res.conflicts:
                    block_reasons.append(f"[{sys_name.upper()}] Estado do sistema classificado como {res.status.value}.")
            elif res.status in (DependencyStatus.EXISTING, DependencyStatus.REUSABLE):
                system_actions[sys_name] = "REUSE"
            elif res.status == DependencyStatus.ABSENT:
                system_actions[sys_name] = "CREATE"

        return can_proceed, system_actions, block_reasons
