from typing import Dict, Any, List
from app.models.vlan_intent import VlanIntent, PropagationPolicy
from app.models.desired_state import DesiredState

class DesiredStateService:
    @staticmethod
    def generate_desired_state(intent: VlanIntent, path: List[str]) -> Dict[str, DesiredState]:
        """
        Converte uma VLAN Intent e um caminho topologico nos DesiredState de cada dispositivo.
        """
        states = {}
        
        # All path switches need the VLAN created
        for sw in path:
            states[sw] = DesiredState(
                device_id=sw,
                vlans={intent.vlan_id: {"name": intent.name}},
                interfaces={}
            )

        # Configure access port on target switch
        target_state = states.get(intent.target_switch)
        if target_state:
            target_state.interfaces[intent.target_port] = {
                "mode": intent.target_mode,
                "native_vlan": intent.vlan_id
            }

        # Trunks config along the path
        if intent.propagation == PropagationPolicy.PATH_TO_CORE and len(path) > 1:
            for i in range(len(path) - 1):
                sw_a = path[i]
                sw_b = path[i+1]
                
                states[sw_a].interfaces["Gi0/48"] = {
                    "mode": "trunk",
                    "allowed_vlans": [intent.vlan_id]
                }
                states[sw_b].interfaces["Gi0/48"] = {
                    "mode": "trunk",
                    "allowed_vlans": [intent.vlan_id]
                }

        return states
