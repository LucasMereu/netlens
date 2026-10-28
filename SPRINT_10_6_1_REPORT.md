# RELATÓRIO DO SPRINT 10.6.1 — Controlled Hardware DAG Safety Gate

Este relatório documenta a execução em hardware real, injeção de falhas e rollback verificado no switch Aruba 2930F do LAB (`A22_Aruba-2930F-48G-4SFPP`), IP `172.16.11.90`.

---

## Prova de Validação Física do DAG e Resiliência a Falhas

O script utilitário [`run_hardware_dag.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_hardware_dag.py) realizou com sucesso todas as quatro fases do ciclo transacional:

```text
============================================================
NETLENS SPRINT 10.6.1 — CONTROLLED HARDWARE DAG SAFETY GATE
============================================================

Fase 1
PRODUCTION_APPLY_ENABLED: False
Environment: LAB
Device Identity: MATCH
Baseline: MATCH
SSH: PASS
VLAN 999: ABSENT
Allowlist: PASS
Lock: ACQUIRED
Preflight: PASS

Fase 2
DAG:
  A: CREATE_VLAN_999
  B: VERIFY_STATE

A: SUCCESS
B: SUCCESS

VLAN 999: PRESENT
Name: NETLENS_TEST

Fase 3
ROLLBACK

DELETE_VLAN_999: SUCCESS

VLAN 999: ABSENT
Canonical Drift: 0
Rollback: PASS

Fase 4
FAULT INJECTION

A CREATE_VLAN_999: SUCCESS

B ADD_VLAN_TO_TRUNK:
    Physical execution: NO
    Injected failure: YES
    Result: FAIL
    Reason: CONTROLLED_FAULT_INJECTION

C VERIFY_STATE:
    SKIPPED

ROLLBACK

A DELETE_VLAN_999: SUCCESS

VLAN 999: ABSENT

Identity: MATCH
VLAN: MATCH
Interfaces: MATCH
Topology: MATCH

Canonical Drift: 0

Transaction: ROLLED_BACK

Production mutations: 0
Unexpected physical operations: 0
Final state mutation: 0

HARDWARE DAG SAFETY GATE: PASS
============================================================
```

### Análise da Resiliência a Falhas (Fase 4):
1.  **Orquestração e Execução Físicas:** O nó `A` (`CREATE_VLAN_999`) escreveu com sucesso no switch real.
2.  **Injeção de Falha em B (`ADD_VLAN_TO_TRUNK`):** A falha simulada foi ativada como `CONTROLLED_FAULT_INJECTION` sem enviar comandos físicos à trunk. O nó `C` foi pulado (`SKIPPED`) de forma correta.
3.  **Rollback Transacional Físico:** O motor acionou imediatamente a remoção da VLAN (`DELETE_VLAN_999`) no Aruba.
4.  **Discovery Independente pós-Rollback:** Uma sessão de discovery SSH totalmente nova e independente foi disparada diretamente contra o switch físico `172.16.11.90`, comprovando que a VLAN 999 foi totalmente removida e que o switch físico retornou ao baseline original com **Drift = 0**.

---

## Resultados da Suite de Testes

```text
Ran 125 tests in 0.306s

OK
```
Todos os **125 testes de regressão** rodaram e passaram perfeitamente.
