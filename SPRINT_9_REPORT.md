# RELATÓRIO DO SPRINT 9 — Approval Workflow & Controlled Production Apply

Este relatório descreve a conclusão do Sprint 9, detalhando o isolamento rígido de escrita, máquina de estados transacional, fluxo de aprovações criptográficas de 30 minutos, janelas de mudança e preflights em duas fases.

---

## Estrutura do Projeto Resultante e Arquivos Criados/Modificados

*   **[`app/models/approval.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/approval.py)**: Modelo de aprovações temporais e vinculação criptográfica ao hash do plano.
*   **[`app/models/change_window.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/change_window.py)**: Modelo de janela de mudanças restringindo horário, dispositivo e operações permitidas.
*   **[`app/services/approval_service.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/approval_service.py)**: Controle e validação de expiração e integridade das aprovações.
*   **[`app/services/apply_executor.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/apply_executor.py)**: Executor físico isolado que atua como único ponto de escrita do NetLens.

---

## Métrica de Linhas de Código (Principais Arquivos)

*   **`main.py`**: 16 linhas (congelado)
*   **`app/services/intent_engine.py`**: 535 linhas (frozen)
*   **`app/models/approval.py`**: 51 linhas
*   **`app/models/change_window.py`**: 25 linhas
*   **`app/services/approval_service.py`**: 38 linhas
*   **`app/services/apply_executor.py`**: 176 linhas
*   *Métricas de Teste:* `test_app.py` possui **749 linhas** validando a integridade absoluta dos 98 casos de teste.

---

## Recursos e Mecanismos de Segurança Implementados

1.  **Isolamento Rígido de Escrita (Write Access):** Planner, Reconciliation, DesiredState e ApprovalService foram isolados e não possuem referências ao factory de drivers. Apenas o `ApplyExecutor` pode efetivamente iniciar sessões SSH de escrita.
2.  **Aprovações Temporais e Criptográficas:** O `ApprovalRecord` vincula imutavelmente a decisão de aprovação ao hash SHA-256 do plano de mudança. Qualquer alteração ou expiração de 30 minutos invalida a execução (`APPROVAL_EXPIRED`).
3.  **Janelas de Mudança Granulares:** Verificação estrita que barra qualquer execução fora de horários estipulados ou em switches/operações não autorizados explicitamente.
4.  **Preflight em Duas Fases:** Validação de segurança inicial, aquisição de travas em ordem alfabética para prevenir deadlocks, seguida de um segundo preflight para revalidar status operacionais das portas antes de aplicar qualquer comando físico.
5.  **Post-Apply Verification & Reverse Rollback:** Discovery pós-apply confirma a convergência do estado real contra o `DesiredState` (drift = 0). Caso ocorra falha física ou lógica, o executor reverte os comandos na ordem inversa e sinaliza o status `ROLLBACK_FAILED` caso a reversão falhe.

---

## Execução da Suite de Testes

Executamos a regressão completa via `discover`:

```text
Ran 98 tests in 0.260s

OK
```

Todos os 98 testes integrados passaram com sucesso, abrangendo as asserções de baselines anteriores e as 42 novas validações do Sprint 9.
