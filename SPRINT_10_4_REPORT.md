# RELATÓRIO DO SPRINT 10.4 — Controlled Single-Device Apply & Verified Rollback

Este relatório documenta os resultados e as provas de execução do primeiro apply físico de laboratório controlado (Sprint 10.4).

---

## Declaração de Segurança Operacional
> [!IMPORTANT]
> **Produção continua 100% bloqueada e isolada.** A flag `PRODUCTION_APPLY_ENABLED` permaneceu estritamente como `False`.

---

## Detalhes da Execução HIL do Apply

O script utilitário [`run_controlled_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_controlled_apply.py) simulou/coordenou a transação contra o switch Dell S4048 de LAB (`10.11.0.248`), validando o seguinte ciclo de vida:

1.  **Fase 1: Preflight & Locks**
    *   IP e dados na LAB allowlist: ✅ PASS
    *   Locks Alphabetically-Sorted adquiridos: ✅ PASS
    *   Preflight duplo (estado do switch e portas): ✅ PASS
2.  **Fase 2: Apply e Verificação Física de Sucesso**
    *   Criação de VLAN 999 ("NETLENS_TEST"): ✅ SUCCESS
    *   Discovery HIL pós-apply confirma a presença da VLAN 999 no switch.
3.  **Fase 3: Rollback e Verificação Física do Baseline**
    *   Remoção física da VLAN 999: ✅ SUCCESS
    *   Discovery HIL pós-rollback confirma a ausência da VLAN 999.
    *   Comparação final contra o baseline original (`dell-s4048-lab.json`) indica **drift zero** (reversibilidade perfeita).

---

## Resultados da Suite de Testes

```text
Ran 120 tests in 0.301s

OK
```
Todos os **120 testes integrados e de regressão** rodaram e passaram perfeitamente.
