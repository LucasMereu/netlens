from enum import Enum
from typing import Optional

class PropagationPolicy(str, Enum):
    LOCAL = "LOCAL"
    PATH_TO_CORE = "PATH_TO_CORE"
    SITE = "SITE"
    DATACENTER = "DATACENTER"
    CUSTOM = "CUSTOM"

class VlanIntent:
    def __init__(self, vlan_id: int, name: str, target_switch: str, target_port: str, propagation: PropagationPolicy = PropagationPolicy.PATH_TO_CORE, target_mode: str = "access"):
        self.vlan_id = vlan_id
        self.name = name
        self.target_switch = target_switch
        self.target_port = target_port
        self.propagation = propagation
        self.target_mode = target_mode # "access" or "trunk"

    def to_dict(self):
        return {
            "vlan_id": self.vlan_id,
            "name": self.name,
            "target_switch": self.target_switch,
            "target_port": self.target_port,
            "propagation": self.propagation.value if isinstance(self.propagation, PropagationPolicy) else self.propagation,
            "target_mode": self.target_mode
        }
