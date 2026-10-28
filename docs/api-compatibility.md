# Compatibilidade e Contratos de APIs Existentes

Esta documentação descreve as garantias de retrocompatibilidade das APIs do NetLens.

## Preservação de APIs Existentes

As rotas síncronas existentes de auditoria de rede e gerenciamento Dell mantêm rigorosamente os mesmos contratos JSON de entrada e saída.

*   `/api/backup-config` (POST): Permanece estritamente síncrono, aguardando a finalização e retornando o conteúdo bruto da configuração do switch no campo `content`. Isso garante compatibilidade com scripts legados.
*   `/api/dell-alignment/validate` (POST): Mantém a resposta síncrona retornando o status de alinhamento global de VLANs nos switches Core e Acesso.
*   `/api/status` (GET): Retorna a situação de conectividade com Zabbix, Netdisco e LibreNMS.

## Novas Rotas para Execuções Assíncronas

Tarefas futuras que exijam assincronismo (como mutações de rede) farão uso de endpoints específicos para Jobs:

*   `POST /api/jobs`: Submissão de tarefas.
*   `GET /api/jobs`: Listagem de tarefas em andamento.
*   `GET /api/jobs/<job_id>`: Consulta detalhada do progresso e status de uma tarefa específica.
