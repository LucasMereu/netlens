from typing import Optional, List
from app.drivers.transport.base import NetworkTransport
from app.drivers.errors import ConnectionError, TimeoutError
from app.drivers.security.readonly_guard import ReadOnlyCommandGuard

class MockTransport(NetworkTransport):
    def __init__(self, host: str, connect_timeout: float = 10.0, command_timeout: float = 30.0, read_timeout: float = 10.0, idle_timeout: float = 60.0):
        super().__init__(host, connect_timeout, command_timeout, read_timeout, idle_timeout)
        self.connected = False
        self.history: List[str] = []
        self.command_responses = {}
        self.should_timeout = False
        self.platform = None

    def connect(self) -> None:
        if self.should_timeout:
            raise TimeoutError("Conexao simulada excedeu o tempo limite.")
        self.connected = True

    def send(self, data: str) -> None:
        if not self.connected:
            raise ConnectionError("MockTransport nao conectado.")
        self.history.append(data)

    def receive(self) -> str:
        if not self.connected:
            raise ConnectionError("MockTransport nao conectado.")
        return "mock prompt"

    def execute(self, command: str, timeout: Optional[float] = None) -> str:
        if not self.connected:
            raise ConnectionError("MockTransport nao conectado.")
            
        # Call baseline safety validation and command policy validation before execution
        from app.drivers.security.readonly_guard import ProtectedBaselineGuard
        ProtectedBaselineGuard.validate_command(command)
        
        if getattr(self, "platform", None) is not None:
            ReadOnlyCommandGuard.validate_command(self.platform, command)
            
        self.history.append(command)
        
        if self.should_timeout:
            raise TimeoutError("Comando simulado excedeu o tempo limite.")
            
        return self.command_responses.get(command, "Success (Mock)")

    def disconnect(self) -> None:
        self.connected = False
