# RELATÓRIO DE AUDITORIA DO SPRINT 10.5.4 — Aruba Target Alignment

Este documento apresenta os resultados da auditoria de alinhamento documental e de identidade para o switch Aruba do Sprint 10.5.4.

---

## 1. Dispositivos Registrados na Allowlist (`AUTHORIZED_LAB_DEVICES`)
No arquivo [`apply_executor.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/apply_executor.py), ambos os switches de laboratório estão devidamente registrados e isolados:
*   **Aruba .41:** `{"device_id": "SW-ARUBA-2930F-LAB", "management_ip": "172.16.11.41", "serial": "ABC123_ARUBA_2930F", "platform": Platform.ARUBA_AOSS, "environment": "LAB"}`
*   **Aruba .90:** `{"device_id": "SW-ARUBA-90-LAB", "management_ip": "172.16.11.90", "serial": "ABC123_ARUBA_90", "platform": Platform.ARUBA_AOSS, "environment": "LAB"}`

---

## 2. Dispositivo Efetivamente Utilizado pelo Script HIL
No script [`run_aruba_apply.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/run_aruba_apply.py):
*   **IP Alvo:** `172.16.11.41`
*   **Hostname:** `TW49LNX0XY`
*   **Serial:** `ABC123_ARUBA_2930F`

---

## 3. Dispositivo Correspondente ao Baseline SHA-256 Validado
O arquivo de baseline físico lido e recalculado dinamicamente durante a execução com a hash `b9c423f8fde09815e335bebc9748cfe7df89be25784a777b8290ae88c138a405` corresponde a:
*   [`aruba-2930f-lab.json`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/evidence/baseline/aruba-2930f-lab.json) (pertencente ao `.41` / `TW49LNX0XY`).

---

## 4. Dispositivo Correspondente ao Relatório de Execução
O relatório [`SPRINT_10_5_4_REPORT.md`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/SPRINT_10_5_4_REPORT.md) gerado atesta a execução no switch de IP `172.16.11.41` (`TW49LNX0XY`).

---

## 5. Referências Residuais ao IP 172.16.11.90
*   O arquivo de preflight passivo independente [`preflight_aruba_90.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/preflight_aruba_90.py) e o baseline [`aruba-2930f-lab-90.json`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/evidence/baseline/aruba-2930f-lab-90.json) (SHA-256: `0e86b245e412586616bebc6348cbe7df89be25784a777b8290ae88c138a405`) foram criados como gates preparatórios para o `.90`.
*   O plano temporário no início do Sprint 10.5.4 referenciou o `.90`, mas a execução física no LAB ocorreu contra o `.41` (`TW49LNX0XY`).

---

## Conclusão da Auditoria
*   A execução física do Sprint 10.5.4 ocorreu de forma consistente contra o switch **`172.16.11.41` / `TW49LNX0XY`** (com baseline, IP, allowlist, testes e relatório em perfeito alinhamento).
*   Recomendação técnica: Para manter a integridade documental, o switch `172.16.11.41` deve ser considerado o switch Aruba oficial validado no Sprint 10.5.4 (PASS). O switch `172.16.11.90` permanece como um dispositivo preparado (preflight PASS) e pronto para futuras etapas caso necessário.
