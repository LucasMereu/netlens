from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

class ReconciliationState(str, Enum):
    COMPLIANT = "COMPLIANT"    # Desired and Observed states match exactly (DRIFT: 0)
    DRIFT = "DRIFT"            # Objects exist but attributes or templates differ (DRIFT > 0)
    ORPHAN = "ORPHAN"          # Object exists in secondary system but missing in NetBox
    CONFLICT = "CONFLICT"      # Identifier collision (e.g. IP assigned to another host)
    UNKNOWN = "UNKNOWN"        # API endpoint unreachable or error
    STALE = "STALE"            # Telemetry or discovery timestamp expired

@dataclass
class DesiredState:
    hostname: str
    ip: str
    site: str
    model: str
    profile: str
    netbox_role: str
    zabbix_groups: List[str]
    zabbix_templates: List[str]
    librenms_protocol: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hostname": self.hostname,
            "ip": self.ip,
            "site": self.site,
            "model": self.model,
            "profile": self.profile,
            "netbox_role": self.netbox_role,
            "zabbix_groups": self.zabbix_groups,
            "zabbix_templates": self.zabbix_templates,
            "librenms_protocol": self.librenms_protocol
        }

@dataclass
class ObservedState:
    netbox_status: str       # "PRESENT", "ABSENT", "ERROR"
    zabbix_status: str       # "PRESENT", "ABSENT", "ERROR"
    librenms_status: str     # "PRESENT", "ABSENT", "ERROR"
    netdisco_status: str     # "PRESENT", "ABSENT", "STALE", "ERROR"
    netbox_site: Optional[str] = None
    netbox_role: Optional[str] = None
    netbox_ip: Optional[str] = None
    zabbix_groups: List[str] = field(default_factory=list)
    zabbix_templates: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "netbox": {"status": self.netbox_status, "site": self.netbox_site, "role": self.netbox_role, "ip": self.netbox_ip},
            "zabbix": {"status": self.zabbix_status, "groups": self.zabbix_groups, "templates": self.zabbix_templates},
            "librenms": {"status": self.librenms_status},
            "netdisco": {"status": self.netdisco_status}
        }

@dataclass
class DriftDetail:
    system: str
    field: str
    expected: Any
    actual: Any
    classification: str       # "CONFIGURATION_DRIFT", "INVENTORY_DRIFT", "ORPHAN_HOST"
    remediation_available: bool = True
    auto_repair: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "classification": self.classification,
            "remediation_available": self.remediation_available,
            "auto_repair": self.auto_repair
        }

@dataclass
class ReconciliationReportCard:
    plan_id: str
    hostname: str
    ip: str
    state: ReconciliationState
    drift_count: int
    drifts: List[DriftDetail] = field(default_factory=list)
    system_summaries: Dict[str, str] = field(default_factory=dict)
    formatted_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "hostname": self.hostname,
            "ip": self.ip,
            "state": self.state.value if isinstance(self.state, ReconciliationState) else str(self.state),
            "drift_count": self.drift_count,
            "drifts": [d.to_dict() for d in self.drifts],
            "system_summaries": self.system_summaries,
            "formatted_report": self.formatted_report
        }
