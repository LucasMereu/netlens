from typing import List, Optional

class NetworkInterface:
    def __init__(self, device_id: str, name: str, description: Optional[str] = None, admin_status: str = "up", oper_status: str = "up", speed: Optional[str] = None, duplex: str = "full", mode: str = "access", native_vlan: int = 1, allowed_vlans: Optional[List[int]] = None, access_vlan: int = 1, mtu: int = 1500, mac_addresses: Optional[List[str]] = None, lldp_neighbor: Optional[dict] = None, cdp_neighbor: Optional[dict] = None, stp_state: Optional[str] = None, stp_role: Optional[str] = None):
        self.device_id = device_id
        self.name = name
        self.description = description
        self.admin_status = admin_status
        self.oper_status = oper_status
        self.speed = speed
        self.duplex = duplex
        self.mode = mode # "access" or "trunk"
        self.native_vlan = native_vlan
        self.allowed_vlans = allowed_vlans or []
        self.access_vlan = access_vlan
        self.mtu = mtu
        self.mac_addresses = mac_addresses or []
        self.lldp_neighbor = lldp_neighbor
        self.cdp_neighbor = cdp_neighbor
        self.stp_state = stp_state
        self.stp_role = stp_role

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "description": self.description,
            "admin_status": self.admin_status,
            "oper_status": self.oper_status,
            "speed": self.speed,
            "duplex": self.duplex,
            "mode": self.mode,
            "native_vlan": self.native_vlan,
            "allowed_vlans": self.allowed_vlans,
            "access_vlan": self.access_vlan,
            "mtu": self.mtu,
            "mac_addresses": self.mac_addresses,
            "lldp_neighbor": self.lldp_neighbor,
            "cdp_neighbor": self.cdp_neighbor,
            "stp_state": self.stp_state,
            "stp_role": self.stp_role
        }
