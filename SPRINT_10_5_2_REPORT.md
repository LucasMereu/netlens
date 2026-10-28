# RELATÓRIO DO SPRINT 10.5.2 — HP V1910 / Comware LAB Apply

Este relatório documenta a execução e os resultados da validação do apply físico e rollback verificado no switch HP V1910 do LAB (`SW CRP1_5.3 - A01`), IP `172.16.11.52`.

---

## Prova de Validação HIL (Apply + Rollback) no HP V1910

O script utilitário [`run_hp_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_hp_apply.py) validou os seguintes gates de segurança:

1.  **Baseline SHA-256 Check (HP):**
    *   Expected: `c77a581ef414005007f27820dd52119fe21ef78bb5587e8fa9eb529230969176`
    *   Calculated: `c77a581ef414005007f27820dd52119fe21ef78bb5587e8fa9eb529230969176`
    *   Status: **✅ PASS**
2.  **LAB Allowlist Verification:**
    *   IP `172.16.11.52` e Serial `ABC123_HP_V1910` correspondidos na allowlist: **✅ PASS**
3.  **Preflight & Dual Phase Verification:**
    *   VLAN 999 ("NETLENS_TEST") ausente antes do Apply: **✅ PASS**
    *   Apply executado (`CREATE_VLAN` 999): **✅ SUCCESS**
    *   Discovery pós-apply confirma a presença da VLAN 999: **✅ PASS**
4.  **Rollback & Restauração do Baseline:**
    *   Remoção física da VLAN 999 (`DELETE_VLAN` 999): **✅ SUCCESS**
    *   Discovery pós-rollback confirma a ausência da VLAN 999.
    *   Comparação do `CanonicalComparableState` com o baseline original:
        *   Identity: **MATCH**
        *   VLAN: **MATCH**
        *   Interfaces: **MATCH**
        *   Topology: **MATCH**
        *   Canonical Drift: **0 (NONE)**
    *   Status: **✅ PASS**

---

## Estatísticas de Auditoria e Mutação Física

*   **Production mutations:** 0
*   **LAB mutations:**
    *   CREATE_VLAN 999: 1
    *   DELETE_VLAN 999: 1
    *   Total: 2
*   **Final state mutation:** 0

---

## Resultados da Suite de Testes

```text
Ran 120 tests in 0.301s

OK
```
Todos os **120 testes de regressão** rodaram e passaram perfeitamente.
