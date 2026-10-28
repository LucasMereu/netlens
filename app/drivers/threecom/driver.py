from typing import Dict, Any, List, Optional
from app.drivers.comware.driver import ComwareDriver
from app.drivers.transport.ssh import SSHTransport
from app.drivers.transport.mock import MockTransport
from app.models.constants import Platform
import app.clients

class ThreeComDriver(ComwareDriver):
    def __init__(self, identity, username=None, password=None):
        if app.clients.is_mock_mode():
            transport = MockTransport(Platform.COMWARE_V5)
        else:
            transport = SSHTransport(identity.management_ip, username=username, password=password, connect_timeout=30.0)
        super().__init__(identity, username=username, password=password, transport=transport)
