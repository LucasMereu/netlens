# RELATÓRIO DO SPRINT 10.1 — LAB Connectivity & Read-Only Discovery

Este relatório documenta a execução e os resultados da validação em laboratório sob controle estrito (Sprint 10.1).

---

## Declaração Inequívoca de Segurança Operacional

> [!IMPORTANT]
> **Nenhuma alteração de configuração física ou comando mutativo foi executado em produção.** O NetLens operou em modo 100% Read-Only e a flag `PRODUCTION_APPLY_ENABLED` permaneceu configurada como `False`.

---

## Barreiras de Segurança Operacionais Validadas

1.  **Strict LAB Allowlist Check:** O `ApplyExecutor` impediu conexões com qualquer IP que não fizesse parte da lista restrita de laboratório autorizada (`SW-248`, `SW-10`, `SW-2`).
2.  **Guardião de Comandos Read-Only:** A classe `CommandPolicy` foi atualizada e agora barra explicitamente comandos de modo de configuração (ex: `configure terminal`, `system-view`) antes de qualquer interação SSH, disparando a exceção `ValidationError`.
3.  **Geração e Persistência de Evidências JSON:** Cada probe de laboratório salvou um registro estruturado da auditoria no diretório `scratch/evidence/`.

---

## Evidências de Laboratório Geradas

Os seguintes arquivos de log estruturados foram gravados:
*   [dell_os9-lab-01.json](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/evidence/dell_os9-lab-01.json)
*   [hpe_comware-lab-01.json](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/evidence/hpe_comware-lab-01.json)
*   [aruba_aos-s-lab-01.json](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/scratch/evidence/aruba_aos-s-lab-01.json)

---

## Execução da Suite de Testes

Executamos a regressão completa do NetLens:

```text
Ran 114 tests in 0.301s

OK
```

Todos os 114 testes da suíte integrada e os testes de conectividade e segurança de comandos estão verdes e aprovados.
