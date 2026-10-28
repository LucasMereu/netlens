# Abstração de Network Driver e Transporte

Esta documentação descreve a modelagem e separação de transporte e lógica de driver no Sprint 2.

## Transporte Agnóstico de Configuração

Os drivers não interagem com o sistema operacional por meio de pexpect embutido. Toda a comunicação física ou simulada é delegada a uma subclasse de `NetworkTransport`:

*   **SSHTransport:** Trata do login, envio de linhas CLI brutas, recepção e timeouts de execução específicos sem saber o que é uma VLAN ou interface.
*   **MockTransport:** Simula a interação, registrando o histórico de comandos para validação de testes.

## ExpectedState e Idempotência

O driver é encarregado de garantir que operações repetidas (ex: criar uma VLAN já existente) sejam idempotentes ou seguras:
*   **READ & SAFE_WRITE:** Podem sofrer retries automáticos em caso de falha de conexão/timeout.
*   **NON_IDEMPOTENT_WRITE:** Bloqueados de sofrer retries para impedir corrupção.
*   **ExpectedState:** Registra o objeto de validação final (`resource_type`, `resource_id`, `properties`).
