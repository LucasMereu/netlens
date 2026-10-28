# Guia e Estratégia de Testes

Esta documentação descreve as estratégias de testes do NetLens.

## Suite de Testes

A suite de testes está implementada em [test_app.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/test_app.py).

## Testes do Sprint 2

Foram adicionados os seguintes testes na suite:

1.  **test_driver_factory_resolution:** Valida o factory associando `DellDriver` e `MockNetworkDriver` baseado na `DeviceIdentity`.
2.  **test_unsupported_device_factory:** Valida se plataformas não suportadas ou fabricante `UNKNOWN` disparam corretamente a exceção `UnsupportedDeviceError`.
3.  **test_dry_run_safety_barrier:** Garante que quando `dry_run=True` nenhum comando de escrita passe para o transporte. Além disso, garante que mutações com `dry_run=False` exijam `explicit_apply=True`, disparando erro se ausente.
4.  **test_mock_driver_state_simulation_and_rollback:** Executa o ciclo de criação, verificação ativa de alinhamento com `ExpectedState`, aplicação de comandos de rollback e nova validação de remoção de VLAN.
5.  **test_idempotency_creation:** Testa o comportamento de criação dupla de VLAN no switch mock para certificar segurança de mutação.
6.  **test_command_builder_isolation:** Valida a geração CLI do `DellCommandBuilder` de forma 100% isolada e sem conexões.
7.  **test_transport_isolation:** Valida de forma isolada a conexão e histórico do `MockTransport`.
