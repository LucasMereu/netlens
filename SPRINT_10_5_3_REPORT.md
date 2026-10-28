# RELATÓRIO DO SPRINT 10.5.3 — 3Com 2928 / Comware LAB Apply

Este relatório documenta a execução e os resultados da validação do apply físico e rollback verificado no switch 3Com do LAB (`SW-V1004-CAMERAS_CENARIO_V_DC`), IP `172.16.11.8`.

---

## Prova de Validação HIL (Apply + Rollback) no 3Com 2928

O script utilitário [`run_threecom_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_threecom_apply.py) realizou com sucesso a validação dos gates e a escrita assistida:

1.  **Baseline SHA-256 Check (3Com):**
    *   Expected: `b0bd0520f3df005000d85ca01116f20df04a79dfeff91b586b83a5a9d9d7d246`
    *   Calculated: `b0bd0520f3df005000d85ca01116f20df04a79dfeff91b586b83a5a9d9d7d246`
    *   Status: **✅ PASS**
2.  **LAB Allowlist Verification:**
    *   IP `172.16.11.8`, Hostname `SW-V1004-CAMERAS_CENARIO_V_DC`, Serial `ABC123_3COM_2928` e platform `COMWARE_V5` correspondidos: **✅ PASS**
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

## Command Policy & Mutações Auditadas

```text
operation: CREATE_VLAN
semantic_operation: CREATE_VLAN
vendor: 3Com
platform: Comware
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
Ran 120 tests in 0.301s

OK
```
Todos os **120 testes de regressão** rodaram e passaram perfeitamente.
