from typing import Dict, Any, List, Optional
from enum import Enum

class DriftSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class DriftType(Enum):
    UNCHANGED = "UNCHANGED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNKNOWN = "UNKNOWN"

class ObservedState:
    def __init__(self, device: Dict[str, Any], interfaces: List[Dict[str, Any]], vlans: List[Dict[str, Any]], trunks: List[Dict[str, Any]], neighbors: List[Dict[str, Any]], stp: Dict[str, Any], config_revision: str):
        self.device = device
        self.interfaces = interfaces
        self.vlans = vlans
        self.trunks = trunks
        self.neighbors = neighbors
        self.stp = stp
        self.config_revision = config_revision

    def to_dict(self):
        return {
            "device": self.device,
            "interfaces": self.interfaces,
            "vlans": self.vlans,
            "trunks": self.trunks,
            "neighbors": self.neighbors,
            "stp": self.stp,
            "config_revision": self.config_revision
        }

class DesiredState:
    def __init__(self, vlans: Optional[List[Dict[str, Any]]] = None, interfaces: Optional[List[Dict[str, Any]]] = None, trunks: Optional[List[Dict[str, Any]]] = None, policies: Optional[Dict[str, Any]] = None):
        self.vlans = vlans or []
        self.interfaces = interfaces or []
        self.trunks = trunks or []
        self.policies = policies or {}

    def to_dict(self):
        return {
            "vlans": self.vlans,
            "interfaces": self.interfaces,
            "trunks": self.trunks,
            "policies": self.policies
        }

class DriftItem:
    def __init__(self, resource_type: str, resource_id: str, drift_type: DriftType, severity: DriftSeverity, message: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.drift_type = drift_type
        self.severity = severity
        self.message = message

    def to_dict(self):
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "drift_type": self.drift_type.value,
            "severity": self.severity.value,
            "message": self.message
        }

class DriftReport:
    def __init__(self, device_id: str, items: List[DriftItem]):
        self.device_id = device_id
        self.items = items
        self.drifts = items

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "items": [item.to_dict() for item in self.items]
        }

class DriftEngine:
    @staticmethod
    def calculate_drift(observed: ObservedState, desired: DesiredState) -> DriftReport:
        drift_items = []
        
        # 1. Compare VLANs (only properties declared in DesiredState)
        for des_vlan in desired.vlans:
            v_id = des_vlan.get("vlan_id")
            # Find in observed
            obs_vlan = next((v for v in observed.vlans if v.get("vlan_id") == v_id), None)
            if not obs_vlan:
                drift_items.append(DriftItem(
                    resource_type="vlan",
                    resource_id=str(v_id),
                    drift_type=DriftType.REMOVED,
                    severity=DriftSeverity.WARNING,
                    message=f"VLAN {v_id} ausente no equipamento."
                ))
            else:
                # Compare declared properties only (e.g. name)
                if "name" in des_vlan and des_vlan["name"] != obs_vlan.get("name"):
                    drift_items.append(DriftItem(
                        resource_type="vlan",
                        resource_id=str(v_id),
                        drift_type=DriftType.MODIFIED,
                        severity=DriftSeverity.WARNING,
                        message=f"Nome da VLAN {v_id} diverge: Desejado '{des_vlan['name']}', Observado '{obs_vlan.get('name')}'."
                    ))

        # 2. Compare Interfaces
        for des_if in desired.interfaces:
            if_name = des_if.get("name")
            obs_if = next((i for i in observed.interfaces if i.get("name") == if_name), None)
            if not obs_if:
                drift_items.append(DriftItem(
                    resource_type="interface",
                    resource_id=if_name,
                    drift_type=DriftType.REMOVED,
                    severity=DriftSeverity.CRITICAL,
                    message=f"Interface {if_name} nao encontrada no equipamento."
                ))
            else:
                # Check admin_status if specified
                if "admin_status" in des_if and des_if["admin_status"] != obs_if.get("admin_status"):
                    drift_items.append(DriftItem(
                        resource_type="interface",
                        resource_id=if_name,
                        drift_type=DriftType.MODIFIED,
                        severity=DriftSeverity.CRITICAL,
                        message=f"Interface {if_name} com status administrativo incorreto: Desejado '{des_if['admin_status']}', Observado '{obs_if.get('admin_status')}'."
                    ))

        # 3. Compare Trunks
        for des_trunk in desired.trunks:
            port = des_trunk.get("name")
            obs_trunk = next((t for t in observed.trunks if t.get("name") == port), None)
            if not obs_trunk:
                drift_items.append(DriftItem(
                    resource_type="trunk",
                    resource_id=port,
                    drift_type=DriftType.REMOVED,
                    severity=DriftSeverity.WARNING,
                    message=f"Interface {port} nao esta configurada em modo trunk no equipamento."
                ))
            else:
                # Check allowed VLANs
                if "allowed_vlans" in des_trunk:
                    for v in des_trunk["allowed_vlans"]:
                        if v not in obs_trunk.get("allowed_vlans", []):
                            drift_items.append(DriftItem(
                                resource_type="trunk",
                                resource_id=port,
                                drift_type=DriftType.MODIFIED,
                                severity=DriftSeverity.WARNING,
                                message=f"Trunk {port} nao permite a VLAN desejada {v}."
                            ))

        return DriftReport(observed.device.get("device_id", "unknown"), drift_items)
