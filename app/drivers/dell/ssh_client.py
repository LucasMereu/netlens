import pexpect
from app.utils.logging import get_logger

logger = get_logger("dell_ssh_client")

class DellSSHClient:
    def __init__(self, ip, username, password, timeout=15):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.child = None

    def connect(self):
        ssh_cmd = (
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 "
            f"-o HostKeyAlgorithms=+ssh-rsa "
            f"-o PubkeyAcceptedAlgorithms=+ssh-rsa "
            f"-o Ciphers=+aes128-cbc,aes256-cbc,3des-cbc "
            f"{self.username}@{self.ip}"
        )
        logger.info(f"Conectando ao switch Dell {self.ip} via pexpect...")
        self.child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=self.timeout)

        # Espera por senha ou prompt
        idx = self.child.expect([r"(?i)password:", r"yes/no", pexpect.EOF, pexpect.TIMEOUT])
        if idx == 1:
            self.child.sendline("yes")
            self.child.expect(r"(?i)password:")
            self.child.sendline(self.password)
        elif idx == 0:
            self.child.sendline(self.password)
        elif idx == 2:
            raise Exception("Conexao SSH fechada imediatamente pelo switch.")
        elif idx == 3:
            raise Exception("Timeout aguardando solicitacao de senha.")

        # Verifica se logou (espera prompt)
        prompt_idx = self.child.expect([r"#", r">", r"\]", r"(?i)permission denied", pexpect.TIMEOUT], timeout=10)
        if prompt_idx == 3:
            self.child.close()
            raise Exception("Permissao negada (usuario ou senha incorretos).")
        elif prompt_idx == 4:
            self.child.close()
            raise Exception("Timeout aguardando prompt de comando do switch.")

        # Desabilita paginacao
        self.child.sendline("terminal length 0")
        self.child.expect([r"#", r">"])
        logger.info(f"Conectado com sucesso ao switch Dell {self.ip}")

    def execute_command(self, command, timeout=30):
        if not self.child:
            raise Exception("SSH Client nao conectado.")
        self.child.sendline(command)
        self.child.expect(command)
        self.child.expect([r"#", r">"], timeout=timeout)
        return self.child.before

    def disconnect(self):
        if self.child:
            try:
                self.child.sendline("quit")
                self.child.close()
            except:
                pass
            self.child = None
            logger.info(f"Desconectado do switch Dell {self.ip}")
