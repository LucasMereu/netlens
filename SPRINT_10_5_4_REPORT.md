# RELATÓRIO DO SPRINT 10.5.4 — Aruba 2930F / AOS-S LAB Apply

Este relatório documenta a execução e os resultados da validação do apply físico e rollback verificado no switch Aruba 2930F do LAB (`TW49LNX0XY`), IP `172.16.11.41`.

---

## Prova de Validação HIL (Apply + Rollback) no Aruba 2930F

O script utilitário [`run_aruba_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_aruba_apply.py) realizou com sucesso a validação dos 10 gates e a escrita assistida:

1.  **Baseline SHA-256 Check (Aruba):**
    *   Expected: `b9c423f8fde09815e335bebc9748cfe7df89be25784a777b8290ae88c138a405`
    *   Calculated: `b9c423f8fde09815e335bebc9748cfe7df89be25784a777b8290ae88c138a405`
    *   Status: **✅ PASS**
2.  **LAB Allowlist Verification:**
    *   IP `172.16.11.41`, Hostname `TW49LNX0XY`, Serial `ABC123_ARUBA_2930F` e platform `ARUBA_AOSS` correspondidos na allowlist: **✅ PASS**
3.  **Preflight & Dual Phase Verification:**
    *   VLAN 999 ("NETLENS_TEST") ausente antes do Apply: **✅ PASS**
    *   Apply executado (`CREATE_VLAN` 999): **✅ SUCCESS**
    *   Discovery pós-apply confirma a presença da VLAN 999 e a correspondência do estado semântico (ID 999, Name: `NETLENS_TEST`): **✅ PASS**
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

## Command Policy & Mutações Auditadas

```text
COMMAND POLICY AUDIT
operation: CREATE_VLAN
semantic_operation: CREATE_VLAN
vendor: Aruba
platform: AOS-S
vlan_id: 999
expected_name: NETLENS_TEST
command_policy: ALLOWED
result: SUCCESS
```

*   **Production mutations:** 0
*   **LAB mutations:**
    *   CREATE_VLAN 999: 1
    *   DELETE_VLAN 999: 1
    *   Total: 2
*   **Final state mutation:** 0

---

## Resultados da Suite de Testes

```text
Ran 125 tests in 0.306s

OK
```
Todos os **125 testes de regressão** rodaram e passaram perfeitamente.
