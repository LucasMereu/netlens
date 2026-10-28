# RELATÓRIO DO SPRINT 3 — VLAN Intent Engine & Topology-Aware Planning

Este relatório descreve a conclusão do Sprint 3, detalhando o design e a implementação do **VlanIntentEngine** para planejar de forma declarativa e inteligente a criação e propagação de VLANs no NetLens.

---

## Estrutura do Projeto Resultante e Arquivos Criados

*   **[`app/models/vlan_intent.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/vlan_intent.py)**: Definição de `VlanIntent` e política de propagação `PropagationPolicy` (LOCAL, PATH_TO_CORE, SITE, DATACENTER, CUSTOM).
*   **[`app/models/command_plan.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/command_plan.py)**: Atualizado para incluir `BeforeState` para preservação de configurações no rollback.
*   **[`app/models/change_plan.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/models/change_plan.py)**: Atualizado com `ChangeImpact` e fluxo de transição de aprovação (`approve`, `apply`).
*   **[`app/services/intent_engine.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/intent_engine.py)**: Core `VlanIntentEngine` contendo cálculo de caminho físico, validações de grafos/trunks e reversão de rollback.
*   **[`app/routes/intent_routes.py`](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/routes/intent_routes.py)**: Endpoints HTTP de intenção e planos de alteração.

---

## Métrica de Linhas de Código (Principais Arquivos)

Verificamos os tamanhos dos arquivos principais do NetLens após a conclusão do Sprint 3:

*   **`main.py`**: 16 linhas
*   **`app/services/vlan_service.py`**: 124 linhas
*   **`app/services/job_service.py`**: 69 linhas
*   **`app/services/intent_engine.py`**: 310 linhas (Motor robusto de inteligência de VLANs)
*   **`app/drivers/base_driver.py`**: 107 linhas
*   **`app/drivers/dell/driver.py`**: 183 linhas
*   **`app/drivers/dell/ssh_client.py`**: 69 linhas
*   **`app/drivers/dell/parser.py`**: 35 linhas
*   **`app/database/connection_pool.py`**: 194 linhas
*   *Métricas de Testes:* `test_app.py` possui **442 linhas** cobrindo todos os cenários de topologia, conflitos e rollback.

---

## Recursos e Validações Implementadas

1.  **Caminho e Abortar em Unreachable:** O motor de caminhos traça dinamicamente a rota física do switch de acesso de destino ao switch Core. Se a rota não puder ser fechada, o plano é abortado retornando erro `PATH_UNREACHABLE`.
2.  **Validação de Conflito de VLAN (Caso A, B e C):**
    *   *Caso A (VLAN Inexistente):* Gera plano de criação.
    *   *Caso B (VLAN Existe com mesmo nome):* Pula a etapa de criação (idempotência).
    *   *Caso C (VLAN Existe com nome diferente):* Aborta preventivamente o plano para evitar sobreposição indesejada.
3.  **Validação de Trunks Simétricos:** Compara as VLANs permitidas nos dois lados do link. Se ambos já possuem a VLAN, nenhum comando é gerado. Se desalinhados, gera comando simétrico para ambas as pontas.
4.  **Ordem de Execução por Fases:** Mapeia a execução do plano em fases ordenadas: Criar VLANs -> Validar VLANs -> Alterar Trunks -> Validar Trunks -> Configurar Porta Acesso -> Validar Porta Acesso.
5.  **Rollback Reverso & Preservação:**
    *   A fila de comandos de rollback é executada na ordem inversa das fases (desfaz a porta de acesso primeiro, depois trunks, e depois a VLAN).
    *   *Preservação de VLANs pré-existentes:* Se a VLAN já existia no switch antes do ChangePlan (Caso B), o rollback é instruído via `BeforeState` a **não deletar** a VLAN do switch.
6.  **Plan Explanation & ChangeImpact:** Apresenta justificativa legível contendo hops do caminho físico e estatísticas de impacto detalhadas antes da aprovação.

---

## Execução da Suite de Testes

Executamos o comando de testes automatizados `python -m unittest test_app.py`. **Todos os 13 testes passaram (OK)** em menos de 2 segundos.

*   `test_path_unreachable_abort` (Passou - Abortou com erro PATH_UNREACHABLE)
*   `test_vlan_intent_path_planning` (Passou - Mapeou corretamente o caminho CORE ⇄ DIST ⇄ ACCESS)
*   `test_vlan_name_conflict_abort` (Passou - Abortou preventivamente no conflito de nome)
*   `test_vlan_exists_no_change` (Passou - Idempotência verificada de forma isolada)
*   `test_reverse_rollback_and_preexisting_preservation` (Passou - Executou rollback inverso e preservou a VLAN pré-existente no Core)
*   *Testes baseline e drivers de transporte* (Passou)

---

## Recomendações para o Sprint 4
No Sprint 4, com o VlanIntentEngine validado contra o MockNetworkDriver, poderemos dar o próximo passo: habilitar a execução real dos planos de alteração gerados nos switches Dell físicos em produção, ativando as validações pós-apply no hardware.
