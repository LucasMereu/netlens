# RELATÓRIO DO SPRINT 7 — Network Source of Truth & Reconciliation

Este relatório descreve a conclusão do Sprint 7, detalhando a arquitetura de reconciliação de múltiplas fontes, matriz de autoridade explícita e governança de dados cruzados.

---

## Estrutura do Projeto Resultante e Arquivos Criados/Modificados

*   **[`app/models/canonical_state.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/canonical_state.py)**: `CanonicalObservedState` encapsulando metadados de freshness e confidence.
*   **[`app/services/source_of_truth_service.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/source_of_truth_service.py)**: Matriz explícita de autoridade.
*   **[`app/services/correlation_service.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/correlation_service.py)**: Correlação e etiquetamento de confianças de atributos.
*   **[`app/services/reconciliation_engine.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/reconciliation_engine.py)**: Motor de reconciliação com políticas de bloqueio contra dados stale ou divergentes.

---

## Métrica de Linhas de Código (Principais Arquivos)

Verificamos os tamanhos dos arquivos principais do NetLens após a conclusão do Sprint 7:

*   **`main.py`**: 16 linhas
*   **`app/models/canonical_state.py`**: 41 linhas
*   **`app/services/source_of_truth_service.py`**: 19 linhas
*   **`app/services/correlation_service.py`**: 48 linhas
*   **`app/services/reconciliation_engine.py`**: 38 linhas
*   *Métricas de Teste:* `test_app.py` possui **308 linhas** cobrindo a validação matricial.

---

## Matriz de Autoridade e Governança

Definimos formalmente a hierarquia de fontes de verdade para evitar decisões implícitas ou arbitrárias:

*   **Hostname / Management IP:** Autoridade do NetBox.
*   **Serial / Platform / Manufacturer:** Autoridade do hardware real do switch.
*   **Topology:** Autoridade do Netdisco (cabeamento real/LLDP).
*   **Interface status / Telemetry:** Autoridade compartilhada entre hardware e LibreNMS.
*   **Availability:** Autoridade do Zabbix.

---

## Execução da Suite de Testes

Executamos a regressão canônica via `unittest discover`:

```text
Ran 19 tests in 0.207s

OK
```

Todos os 19 testes integrados passaram (13 do baseline do Sprint 6 + 6 novos testes do Reconciliation Engine):
*   `test_conflicting_sources_never_generate_changeplan` (Garante que conflitos gerem `BLOCK` preventivo)
*   `test_stale_source_blocks_reconciliation` (Garante que dados mais antigos que 24h entrem em `STALE` e bloqueiem o apply)
*   `test_unknown_state_blocks_apply` (Garante que status `UNKNOWN` impeça execuções)
*   `test_source_authority_is_not_silent` (Valida a exatidão da matriz de autoridade)
*   `test_readonly_external_clients` (Valida o isolamento arquitetural de leitura)
*   `test_no_mutation_path_from_reconciliation` (Garante que o motor de reconciliação permaneça 100% read-only)
