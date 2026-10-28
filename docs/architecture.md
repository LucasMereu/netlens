# Arquitetura do Sistema — SPRINT 2

Esta documentação descreve a arquitetura do NetLens estendida no Sprint 2 para incluir suporte a abstrações de rede baseadas em Intenções e múltiplos drivers.

## Fluxo Conceitual Completo

```text
                  NETLENS (HTTP)
                     │
                     ▼
                  SERVICE
                     │
                     ▼
              DRIVER FACTORY
                     │
                     ▼
              NETWORK DRIVER (Capabilities)
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
      Discovery  Configuration Validation
                     │
                     ▼
                CommandPlan (Operations / Rollback)
                     │
             ┌───────┴───────┐
             ▼               ▼
          Dry Run          Apply (Double Barrier check)
                             │
                             ▼
                         Transport (SSH / Mock / API)
                             │
                             ▼
                           SWITCH
                             │
                             ▼
                        ExpectedState
                             │
                             ▼
                         Validation
```

## Separação de Conceitos

*   **Platform vs Vendor:** Dispositivos são identificados pela tupla `DeviceIdentity` contendo o fabricante (ex: `HPE`) e o sistema operacional correspondente (ex: `Platform.HPE_COMWARE`), garantindo que o driver correto seja selecionado.
*   **Double Barrier Protection:** Operações de escrita exigem `dry_run=False` associado com `explicit_apply=True`. Qualquer chamada de gravação sem esse flag explícito gera uma falha de validação segura por padrão.
*   **ExpectedState:** Mutações geram uma assinatura de estado futuro para permitir que pós-validações ativas comparem a leitura real do switch com as premissas planejadas.
