# RELATÓRIO DO SPRINT 6 — Controlled Multi-Vendor Apply & Transaction Controller

Este relatório descreve a conclusão do Sprint 6, detalhando a evolução do NetLens para um controlador transacional de rede multivendor, com checagens de risco e mitigação de deadlocks.

---

## Estrutura do Projeto Resultante e Arquivos Criados/Modificados

*   **[`app/services/risk_service.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/risk_service.py)**: `RiskService` avaliando a gravidade operacional das mudanças semânticas.
*   **[`app/models/change_plan.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/change_plan.py)**: Atualizado com transições de estado para a máquina transacional e hashes de verificação de aprovação.
*   **[`app/services/intent_engine.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/intent_engine.py)**: Incorpora ordenação determinística de locks por switches e validações de portas de acesso e trunks entre fases de apply.

---

## Métrica de Linhas de Código (Principais Arquivos)

Verificamos os tamanhos dos arquivos principais do NetLens após a conclusão do Sprint 6:

*   **`main.py`**: 16 linhas
*   **`app/services/intent_engine.py`**: 535 linhas
*   **`app/services/risk_service.py`**: 34 linhas
*   **`app/models/change_plan.py`**: 103 linhas
*   *Métricas de Teste:* `test_app.py` possui **267 linhas** validando integridade de hashes de planos, prevenção de deadlocks, e rollbacks de desastre.

---

## Recursos de Controle Transacional Implementados

1.  **Ordenação de Locks contra Deadlocks:** Antes de executar qualquer ação, os switches alvos são ordenados alfabeticamente por `device_id`. A aquisição sequencial evita condições de corrida/espera circular entre jobs paralelos.
2.  **Integridade por Hash de Aprovação:** O `ChangePlan` armazena o `plan_hash` no momento de aprovação. Qualquer tentativa de alteração manual após a aprovação que mude os comandos gera rejeição imediata com `PLANO_MODIFICADO`.
3.  **Avaliação de Risco Dinâmica:** O `RiskService` analisa as operações semânticas associadas ao plano e atribui a classificação de risco proporcional (`low` para criação de VLAN, `medium` para trunks, `high` para modificação de portas de acesso).
4.  **Validação Operacional na Execução:** Durante o apply, checa o estado operacional (`oper_status`) do switch. Se uma porta alvo estiver inesperadamente `DOWN`, a transação é cancelada antes de qualquer modificação física.
5.  **Rollback de Desastre por Fases:** Caso ocorra falha física em uma das fases de execução em qualquer um dos switches, o motor reverte toda a transação executando o rollback na ordem inversa (porta de acesso -> trunks -> vlan), garantindo o retorno ao estado ObservedState original.

---

## Execução da Suite de Testes

Executamos o comando de testes automatizados `venv/bin/python3 -m unittest test_app.py`. **Todos os 9 testes passaram com sucesso (OK)** em 0.207s.

*   `test_apply_rejects_modified_plan` (Passou - Barrou apply de plano com hash inconsistente)
*   `test_lock_order_prevents_deadlock` (Passou - Garantiu ordenação determinística de locks)
*   `test_operational_state_changed_before_apply` (Passou - Abortou apply por interface DOWN)
*   `test_disaster_recovery_rollback` (Passou - Reverteu todas as modificações em caso de falha de fase)
*   `test_readonly_command_guard` (Passou)
