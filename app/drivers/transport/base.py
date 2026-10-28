from abc import ABC, abstractmethod
from typing import Optional

class NetworkTransport(ABC):
    def __init__(self, host: str, connect_timeout: float = 10.0, command_timeout: float = 30.0, read_timeout: float = 10.0, idle_timeout: float = 60.0):
        self.host = host
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.read_timeout = read_timeout
        self.idle_timeout = idle_timeout

    @abstractmethod
    def connect(self) -> None:
        """Estabelece conexao."""
        pass

    @abstractmethod
    def send(self, data: str) -> None:
        """Envia dados sem esperar retorno."""
        pass

    @abstractmethod
    def receive(self) -> str:
        """Recebe dados."""
        pass

    @abstractmethod
    def execute(self, command: str, timeout: Optional[float] = None) -> str:
        """Envia um comando e retorna o resultado."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Fecha a conexao."""
        pass
