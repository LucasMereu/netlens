# Sistema de Jobs e Processamento Assíncrono

Esta documentação descreve o funcionamento do sistema de processamento de tarefas em segundo plano (Jobs).

## Execuções em Background

Operações potencialmente demoradas (como backups ou varreduras completas) não devem bloquear a requisição HTTP. O `JobService` (em [job_service.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/job_service.py)) gerencia essa execução em threads de background de forma isolada.

## Abstração e Estados do Job

Cada tarefa é mapeada pelo modelo `Job`, que assume os seguintes estados:

*   `PENDING`: Aguardando processamento.
*   `RUNNING`: Executando em uma thread dedicada.
*   `SUCCESS`: Concluído com sucesso.
*   `FAILED`: Falha na execução (com log e mensagem de erro).
*   `CANCELLED`: Interrompido.
*   `ROLLBACK`: Retornado ao estado anterior após falha.

## Fila e Limites do Executor

*   O processamento utiliza um `ThreadPoolExecutor` com um limite configurável (padrão de `5` workers simultâneos) para evitar a saturação de conexões SSH e de banco.
*   Cada Job é submetido com um timeout limite para evitar travamento de threads.
*   **Nota de Dívida Técnica:** A fila é temporariamente mantida na memória do processo do Flask. Reiniciar a aplicação fará com que Jobs ativos ou pendentes sejam perdidos. Em sprints futuros, essa infraestrutura será migrada para uma fila de mensageria persistente baseada em Celery/Redis.
