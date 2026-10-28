import pexpect
from typing import Optional
from app.drivers.transport.base import NetworkTransport
from app.drivers.errors import ConnectionError, AuthenticationError, TimeoutError
from app.drivers.security.readonly_guard import ReadOnlyCommandGuard
from app.utils.logging import get_logger

logger = get_logger("ssh_transport")

class SSHTransport(NetworkTransport):
    def __init__(self, host: str, username: str, password: str, connect_timeout: float = 10.0, command_timeout: float = 30.0, read_timeout: float = 10.0, idle_timeout: float = 60.0):
        super().__init__(host, connect_timeout, command_timeout, read_timeout, idle_timeout)
        self.username = username
        self.password = password
        self.child = None
        self.platform = None

    def connect(self) -> None:
        ssh_cmd = (
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 "
            f"-o HostKeyAlgorithms=+ssh-rsa "
            f"-o PubkeyAcceptedAlgorithms=+ssh-rsa "
            f"-o Ciphers=+aes128-cbc,aes256-cbc,3des-cbc "
            f"{self.username}@{self.host}"
        )
        logger.info(f"Iniciando SSH para {self.host} com connect_timeout={self.connect_timeout}...")
        try:
            self.child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=self.connect_timeout)
            
            idx = self.child.expect([r"(?i)password:", r"yes/no", pexpect.EOF, pexpect.TIMEOUT])
            if idx == 1:
                self.child.sendline("yes")
                self.child.expect(r"(?i)password:", timeout=self.connect_timeout)
                self.child.sendline(self.password)
            elif idx == 0:
                self.child.sendline(self.password)
            elif idx == 2:
                raise ConnectionError("Conexao SSH encerrada pelo host remoto.")
            elif idx == 3:
                raise TimeoutError("Excedido tempo de conexao aguardando prompt de senha.")

            prompt_idx = self.child.expect([r"#", r">", r"\]", r"(?i)permission denied", pexpect.TIMEOUT], timeout=self.connect_timeout)
            if prompt_idx == 3:
                self.child.close()
                raise AuthenticationError("Falha de autenticacao: senha/usuario incorretos.")
            elif prompt_idx == 4:
                self.child.close()
                raise TimeoutError("Excedido tempo limite aguardando prompt do shell.")

            self.child.sendline("terminal length 0")
            self.child.expect([r"#", r">"])
        except pexpect.TIMEOUT as te:
            raise TimeoutError(f"Timeout na conexao SSH com {self.host}: {te}")
        except Exception as e:
            if not isinstance(e, (ConnectionError, AuthenticationError, TimeoutError)):
                raise ConnectionError(f"Erro ao conectar via SSH: {e}")
            raise e

    def send(self, data: str) -> None:
        if not self.child:
            raise ConnectionError("Transporte nao conectado.")
        self.child.sendline(data)

    def receive(self) -> str:
        if not self.child:
            raise ConnectionError("Transporte nao conectado.")
        try:
            self.child.expect([r"#", r">"], timeout=self.read_timeout)
            return self.child.before
        except pexpect.TIMEOUT:
            raise TimeoutError("Excedido tempo limite para leitura de dados.")

    def execute(self, command: str, timeout: Optional[float] = None) -> str:
        if not self.child:
            raise ConnectionError("Transporte nao conectado.")
            
        # Call baseline safety validation and command policy validation before execution
        from app.drivers.security.readonly_guard import ProtectedBaselineGuard
        ProtectedBaselineGuard.validate_command(command)
        
        if getattr(self, "platform", None) is not None:
            ReadOnlyCommandGuard.validate_command(self.platform, command)
            
        exec_timeout = timeout or self.command_timeout
        try:
            self.child.sendline(command)
            self.child.expect(command)
            self.child.expect([r"#", r">", r"\]"], timeout=exec_timeout)
            return self.child.before
        except pexpect.TIMEOUT:
            raise TimeoutError(f"Comando '{command}' excedeu o tempo limite de execucao ({exec_timeout}s).")
        except Exception as e:
            raise ConnectionError(f"Falha de transporte ao executar comando: {e}")

    def disconnect(self) -> None:
        if self.child:
            try:
                self.child.sendline("quit")
                self.child.close()
            except:
                pass
            self.child = None
            logger.info(f"SSH desconectado de {self.host}")
