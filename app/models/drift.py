from typing import List, Dict, Any, Tuple
from app.models.canonical_state import CanonicalObservedState
from app.models.desired_state import DesiredState

class SemanticDrift:
    def __init__(self, attribute: str, key: str, old_value: Any, new_value: Any, severity: str = "WARNING"):
        self.attribute = attribute # vlan, interface
        self.key = key # e.g. "3999", "Gi1/0/48"
        self.old_value = old_value
        self.new_value = new_value
        self.severity = severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribute": self.attribute,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "severity": self.severity
        }

class DriftCalculator:
    @staticmethod
    def calculate(observed: CanonicalObservedState, desired: DesiredState) -> List[SemanticDrift]:
        drifts = []
        
        # 1. VLAN drifts
        obs_vlans = {int(v["vlan_id"]): v["name"] for v in observed.vlans}
        for vlan_id, des_vlan in desired.vlans.items():
            obs_name = obs_vlans.get(vlan_id)
            if obs_name is None:
                drifts.append(SemanticDrift("vlan", str(vlan_id), None, des_vlan.get("name"), "WARNING"))
            elif obs_name != des_vlan.get("name"):
                drifts.append(SemanticDrift("vlan_name", str(vlan_id), obs_name, des_vlan.get("name"), "INFO"))

        # 2. Interface drifts
        obs_interfaces = {i["name"]: i for i in observed.interfaces}
        for if_name, des_if in desired.interfaces.items():
            obs_if = obs_interfaces.get(if_name, {})
            
            # Mode drift
            obs_mode = obs_if.get("mode")
            des_mode = des_if.get("mode")
            if des_mode and obs_mode != des_mode:
                drifts.append(SemanticDrift("interface_mode", if_name, obs_mode, des_mode, "HIGH"))

            # Access VLAN
            obs_vlan = obs_if.get("native_vlan")
            des_vlan = des_if.get("native_vlan")
            if des_vlan and obs_vlan != des_vlan:
                drifts.append(SemanticDrift("interface_access_vlan", if_name, obs_vlan, des_vlan, "HIGH"))
                
            # Allowed VLANs (Trunks)
            obs_allowed = set(obs_if.get("allowed_vlans", []))
            des_allowed = set(des_if.get("allowed_vlans", []))
            if des_allowed and not des_allowed.issubset(obs_allowed):
                drifts.append(SemanticDrift("interface_trunk_vlans", if_name, list(obs_allowed), list(des_allowed), "MEDIUM"))

        return drifts
