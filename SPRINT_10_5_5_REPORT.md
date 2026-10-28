# RELATÓRIO DO SPRINT 10.5.5 — HPE 1820 PoE 24G Capability Assessment

Este relatório documenta a descoberta passiva, mapeamento de portas e trava de capacidades do switch HPE 1820 PoE 24G (modelo `J9983A`) no laboratório.

---

## Resultados da Descoberta Passiva nos 3 Switches

O script utilitário [`assess_hpe1820_capabilities.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/assess_hpe1820_capabilities.py) obteve as assinaturas e a comprovação empírica nos três equipamentos:

1.  **172.16.11.33 (CORP_POe_ALMOX-GERAL):**
    *   TCP/22 (SSH): **CLOSED**
    *   TCP/23 (Telnet): **CLOSED**
    *   TCP/80 (HTTP) & TCP/443 (HTTPS): **OPEN**
    *   Status de Descoberta: **✅ PASS**
    *   Baseline SHA-256: `5635d5e9990c8036b1b36f6dc1073616290e0039aba1747c419a0060d86e8712`
2.  **172.16.11.74 (PROD01-LJ-M01-IP10.11.0.200):**
    *   TCP/22 (SSH): **CLOSED**
    *   TCP/23 (Telnet): **CLOSED**
    *   TCP/80 (HTTP) & TCP/443 (HTTPS): **OPEN**
    *   Status de Descoberta: **✅ PASS**
    *   Baseline SHA-256: `7ddc7224e15b489b641d86ffbb0dedd40197ab24d9bb39eae018d76854e4b398`
3.  **172.16.11.82 (CORP_07_VERDE_M07_IP10.11.0.206):**
    *   TCP/22 (SSH): **CLOSED**
    *   TCP/23 (Telnet): **CLOSED**
    *   TCP/80 (HTTP) & TCP/443 (HTTPS): **OPEN**
    *   Status de Descoberta: **✅ PASS**
    *   Baseline SHA-256: `f0b116868561df93adbafb3c05597b6df89d5b3cffd2cb7ea54b0597e05f9597`

---

## Registro Arquitetural das Travas no NetLens

Conforme exigência, os switches HPE 1820 foram declarados no core com a seguinte parametrização de segurança:
```text
HPE 1820:
  Discovery:        SUPPORTED
  Canonical State:  SUPPORTED
  Baseline:         SUPPORTED
  Apply:            BLOCKED
  Rollback:         BLOCKED
```
*   **Mutações físicas em laboratório:** 0
*   **Mutações físicas em produção:** 0

---

## Resultados da Suite de Testes

```text
Ran 125 tests in 0.306s

OK
```
Todos os **125 testes de regressão** rodaram e passaram perfeitamente.
