from typing import Dict, Any, Optional
from app.models.device import DeviceIdentity

class CanonicalDevice:
    def __init__(self, canonical_id: str, serial: Optional[str] = None, management_ip: Optional[str] = None, manufacturer: Optional[str] = None, platform: Optional[str] = None):
        self.canonical_id = canonical_id
        self.serial = serial
        self.management_ip = management_ip
        self.manufacturer = manufacturer
        self.platform = platform
        self.source_ids: Dict[str, Any] = {} # netbox, netdisco, librenms, zabbix
