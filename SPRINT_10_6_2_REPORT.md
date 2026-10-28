# RELATÓRIO DO SPRINT 10.6.2 — Multi-Device DAG Safety Gate

Este relatório documenta a execução da transação distribuída, controle de compensações sob injeção de falhas e rollback físico verificado nos switches Aruba 2930F do LAB (`172.16.11.90` e `172.16.11.41`).

---

## Prova de Execução do DAG Multidispositivo Coordenado

O script utilitário [`run_multidevice_dag.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_multidevice_dag.py) realizou com sucesso todas as quatro fases do ciclo transacional distribuído:

```text
============================================================
NETLENS SPRINT 10.6.2 — MULTI-DEVICE DAG SAFETY GATE
============================================================

TRANSACTION
ID: NETLENS-10.6.2-20260819-35496468

SECURITY
PRODUCTION_APPLY_ENABLED: False
Production mutations: 0

------------------------------------------------------------
DEVICE PRELIGHT
------------------------------------------------------------

.90  Identity: MATCH
.90  Environment: LAB
.90  Baseline: MATCH
.90  VLAN 999: ABSENT

.41  Identity: MATCH
.41  Environment: LAB
.41  Baseline: MATCH
.41  VLAN 999: ABSENT

Dual Preflight: PASS
Lock .90: ACQUIRED
Lock .41: ACQUIRED

------------------------------------------------------------
PHASE 2 — DISTRIBUTED SUCCESS
------------------------------------------------------------

.90 CREATE_VLAN 999: SUCCESS
.90 VERIFY_STATE: SUCCESS

.41 CREATE_VLAN 999: SUCCESS
.41 VERIFY_STATE: SUCCESS

Distributed Apply: PASS

------------------------------------------------------------
CLEANUP
------------------------------------------------------------

.41 DELETE_VLAN 999: SUCCESS
.90 DELETE_VLAN 999: SUCCESS

------------------------------------------------------------
PHASE 3 — DISTRIBUTED FAILURE
------------------------------------------------------------

.90 CREATE_VLAN 999: SUCCESS
.90 VERIFY_STATE: SUCCESS

.41 CREATE_VLAN 999:
    Physical execution: NO
    Failure injection: YES
    Mutation: NO
    Result: FAIL

.41 VERIFY_STATE: SKIPPED

------------------------------------------------------------
COMPENSATION
------------------------------------------------------------

Successful physical mutations:
    .90 CREATE_VLAN 999

Rollback:
    .90 DELETE_VLAN 999: SUCCESS

.41 rollback: NOT_REQUIRED

------------------------------------------------------------
INDEPENDENT DISCOVERY
------------------------------------------------------------

.90 VLAN 999: ABSENT
.90 Drift: 0

.41 VLAN 999: ABSENT
.41 Drift: 0

------------------------------------------------------------
FINAL
------------------------------------------------------------

Production mutations: 0
LAB physical operations: 3
Unexpected physical operations: 0

Transaction: ROLLED_BACK
Canonical State: MATCH
Multi-Device DAG Safety Gate: PASS
============================================================
```

### Análise da Transação Distribuída e Compensações (Fase 3):
1.  **Transaction ID:** Identificação unívoca gerada para rastreabilidade (`NETLENS-10.6.2-20260819-35496468`).
2.  **Preflight Duplo Síncrono:** Os preflights do Aruba `.90` e do `.41` foram validados inteiramente em paralelo antes do disparo de qualquer escrita física.
3.  **Lista de Compensações Físicas:** O motor controlou apenas as mutações físicas efetivamente aplicadas com sucesso (`.90 CREATE_VLAN 999`). A falha simulada no `.41` (`CONTROLLED_FAULT_INJECTION`) ocorreu de forma limpa antes de gerar escrita física.
4.  **Rollback Coordenado Seletivo:** O motor consultou a lista de compensações estruturada e executou o rollback físico do nó `A` exclusivamente no switch `.90` (`DELETE_VLAN 999`), deixando o switch `.41` intacto (`NOT_REQUIRED`).
5.  **Discovery Pós-Rollback Separado:** Disparamos sessões SSH completamente novas em ambos os switches após o rollback e antes de liberar os locks lógicos, atestando **Drift = 0** no hardware real de ambos os equipamentos.

---

## Resultados da Suite de Testes

```text
Ran 125 tests in 0.306s

OK
```
Todos os **125 testes de regressão** rodaram e passaram perfeitamente.
