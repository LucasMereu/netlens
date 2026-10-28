from typing import Dict, Any, List, Optional
from app.drivers.base_driver import NetworkDriver
from app.drivers.transport.mock import MockTransport
from app.models.constants import Platform

class StantonDriver(NetworkDriver):
    __abstractmethods__ = set()
    def __init__(self, identity, username=None, password=None):
        from app.models.capabilities import DeviceCapabilities
        super().__init__(DeviceCapabilities())
        self.identity = identity
        self.transport = MockTransport(Platform.STANTON_OS)
        self.state = {
            "vlans": [{"vlan_id": 1, "name": "default"}],
            "interfaces": [{"name": "port1", "oper_status": "UP", "mode": "access", "native_vlan": 1}]
        }

    def connect(self):
        self.transport.connect()

    def disconnect(self):
        self.transport.disconnect()

    def get_vlan(self, vlan_id: int) -> Optional[Dict[str, Any]]:
        return next((v for v in self.state["vlans"] if v["vlan_id"] == vlan_id), None)

StantonDriver.__abstractmethods__ = set()
