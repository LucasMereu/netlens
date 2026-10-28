# RELATÓRIO DO SPRINT 10.5.1 — HPE 5120 / Comware LAB Apply

Este relatório documenta a execução e os resultados da validação do primeiro apply físico e rollback verificado no switch Comware do LAB (`SWITCH PABX 1`), IP `172.16.11.50`.

---

## Prova de Validação HIL (Apply + Rollback) no Comware

O script utilitário [`run_comware_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_comware_apply.py) validou os seguintes gates de segurança:

1.  **Baseline SHA-256 Check (Comware):**
    *   Expected: `cbcd7936dc6b92ac22b676f7f9bb81ccecbdcb9968209bd559850c10882508f2`
    *   Calculated: `cbcd7936dc6b92ac22b676f7f9bb81ccecbdcb9968209bd559850c10882508f2`
    *   Status: **✅ PASS**
2.  **LAB Allowlist Verification:**
    *   IP `172.16.11.50` e Serial `XYZ123_HP_LAB` correspondidos na allowlist: **✅ PASS**
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

## Resultados da Suite de Testes

```text
Ran 120 tests in 0.301s

OK
```
Todos os **120 testes de regressão** rodaram e passaram perfeitamente.
