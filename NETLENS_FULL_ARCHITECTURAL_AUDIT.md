# NETLENS — RELATÓRIO DE AUDITORIA ARQUITETURAL COMPLETA
**Data:** 18 de Setembro de 2026  
**Ambiente:** macOS / Linux Workstation  
**Natureza da Auditoria:** 100% READ-ONLY / DIAGNÓSTICA (Zero mutations, zero deploys, zero refactors)  
**Versão Base Alvo:** NetLens v10.13.0 (Post-Sprint 10.12.1 Remediation & 10.13.0 Features)

---

## 1. INVENTÁRIO COMPLETO DO PROJETO

### 1.1. Árvore de Diretórios Relevante

```text
.
├── app/
│   ├── analysis/
│   │   ├── bottleneck_detector.py
│   │   ├── path_tracer.py
│   │   ├── ping_monitor.py
│   │   ├── port_event_tracker.py
│   │   ├── stp_tracker.py
│   │   ├── topology_tracker.py
│   │   └── vlan_auditor.py
│   ├── drivers/
│   │   ├── aruba/ (command_builder.py, driver.py, parser.py)
│   │   ├── comware/ (driver.py)
│   │   ├── dell/ (driver.py)
│   │   ├── hp/ (driver.py)
│   │   ├── mock/ (driver.py)
│   │   ├── security/ (readonly_guard.py)
│   │   ├── stanton/ (driver.py)
│   │   ├── threecom/ (driver.py)
│   │   ├── transport/ (ssh.py, mock.py)
│   │   ├── base_driver.py
│   │   ├── errors.py
│   │   ├── factory.py
│   │   └── retry.py
│   ├── models/
│   │   ├── approval.py
│   │   ├── canonical_state.py
│   │   ├── capabilities.py
│   │   ├── change_plan.py
│   │   ├── change_window.py
│   │   ├── command_plan.py
│   │   ├── constants.py
│   │   ├── desired_state.py
│   │   ├── device.py
│   │   ├── device_identity.py
│   │   ├── drift.py
│   │   ├── interface.py
│   │   ├── job.py
│   │   ├── plan_operation.py
│   │   ├── provision_dependency.py
│   │   ├── provision_job.py
│   │   ├── provision_policy.py
│   │   ├── provision_profile.py
│   │   ├── provision_reconciliation.py
│   │   ├── provision_risk.py
│   │   ├── reconciliation.py
│   │   ├── state_models.py
│   │   └── vlan_intent.py
│   ├── policies/
│   │   ├── freshness_policy.py
│   │   └── provision_policy_engine.py
│   ├── routes/
│   │   ├── admin.py
│   │   ├── alerts.py
│   │   ├── auth.py
│   │   ├── bottlenecks.py
│   │   ├── config.py
│   │   ├── dell.py
│   │   ├── intent_routes.py
│   │   ├── inventory.py
│   │   ├── jobs.py
│   │   ├── links.py
│   │   ├── ports.py
│   │   ├── provisioning.py
│   │   ├── reports.py
│   │   ├── status.py
│   │   ├── topology.py
│   │   └── vlans.py
│   ├── services/
│   │   ├── provision_drivers/
│   │   │   ├── librenms_provisioner.py
│   │   │   ├── netbox_provisioner.py
│   │   │   ├── netdisco_provisioner.py
│   │   │   └── zabbix_provisioner.py
│   │   ├── apply_executor.py
│   │   ├── approval_service.py
│   │   ├── audit_service.py
│   │   ├── config_service.py
│   │   ├── correlation_service.py
│   │   ├── desired_state_service.py
│   │   ├── discovery_service.py
│   │   ├── execution_backend.py
│   │   ├── identity_resolver.py
│   │   ├── inprocess_execution_backend.py
│   │   ├── intent_engine.py
│   │   ├── job_engine.py
│   │   ├── job_service.py
│   │   ├── job_store.py
│   │   ├── lock_service.py
│   │   ├── plan_generator.py
│   │   ├── plan_validator.py
│   │   ├── preflight_service.py
│   │   ├── provision_capability_engine.py
│   │   ├── provision_dependency_engine.py
│   │   ├── provision_idempotency_engine.py
│   │   ├── provision_orchestrator.py
│   │   ├── provision_profile_engine.py
│   │   ├── provision_reconciliation.py
│   │   ├── provision_risk_engine.py
│   │   ├── reconciliation_engine.py
│   │   ├── risk_service.py
│   │   ├── secret_service.py
│   │   ├── server_inventory_service.py
│   │   ├── sophos_service.py
│   │   ├── source_of_truth_service.py
│   │   ├── vlan_service.py
│   │   ├── wan_monitor_service.py
│   │   └── wan_speedtest_service.py
│   ├── utils/
│   │   ├── logging.py
│   │   └── sanitizer.py
│   └── __init__.py
├── clients/ (db_client.py, librenms.py, netbox.py, netdisco.py, zabbix.py)
├── static/ (css/, js/vis-network.min.js, marked.min.js)
├── templates/ (index.html, login.html)
├── reports/ (implementation_plan.md, network_audit_report.md, switch_vlan1_audit_report.md)
├── scratch/ (scripts de teste e deploy legados)
├── tests: 27 arquivos test_*.py
├── config.json, config.json.bak, useful_links.json, users.json, jobs.json, provision_plans.json
└── main.py
```

### 1.2. Inventário de Componentes-Chave

| Arquivo | Símbolo / Classe | Responsabilidade Principal | Chamado Por | Quem Chama | Dependências | Estado Atual |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `app/__init__.py` | `create_app()` | Factory do Flask, registro de Blueprints, auth middleware, bootstrap do PingMonitor e JobEngine.recover(). | `main.py`, testes unitários | `PingMonitor.start()`, `JobEngine.recover()` | Flask, Blueprints | **Operacional** (Gera split-brain de threads sob múltiplos workers Gunicorn) |
| `app/services/job_engine.py` | `JobEngine` | Orquestrador assíncrono de jobs de provisioning, transições de ciclo de vida e crash recovery. | `app/routes/provisioning.py` (`/api/v1/provision/apply`, `/jobs/<id>`) | `JobStore`, `InProcessExecutionBackend`, `ProvisionOrchestrator.apply_plan`, `SecretSanitizer` | `ProvisionJob`, `JobStore`, `InProcessExecutionBackend` | **Operacional** |
| `app/services/job_store.py` | `JobStore` | Persistência atômica de jobs em `jobs.json` com flock multi-processo e atomic_transition anti-TOCTOU. | `JobEngine` | `fcntl.flock`, `SecretSanitizer`, `json` | `jobs.json`, `jobs.lock` | **Operacional e Seguro contra vazamento de segredos** |
| `app/services/inprocess_execution_backend.py` | `InProcessExecutionBackend` | Backend assíncrono concreto via `ThreadPoolExecutor(max_workers=5)`. | `JobEngine._get_backend()` | `concurrent.futures.ThreadPoolExecutor` | Python Standard Library | **Operacional localmente** (In-Memory: tarefas não sobrevivem a crash/restart do processo worker) |
| `app/services/provision_orchestrator.py` | `ProvisionOrchestrator` | Geração determinística de ChangePlan, hashing SHA-256, aprovação, verificação quádrupla e dispatch para drivers. | `app/routes/provisioning.py`, `JobEngine` | `ProvisionPolicyEngine`, `ProvisionDependencyEngine`, `ProvisionIdempotencyEngine`, `ProvisionRiskEngine`, Drivers | `provision_plans.json`, `provision_plans.lock`, `BUILTIN_PROFILES` | **Gargalo de concorrência detectado:** mantém `_PLAN_STORE` em memória estática sem recarga atômica antes do `generate_plan`. |
| `app/services/secret_service.py` | `SecretService` | Criptografia em repouso de segredos (snmp_community) usando Fernet (`FERNET:<token>`) com fallback legível para `ENC:<b64>`. | `ProvisionOrchestrator` | `cryptography.fernet.Fernet` | Variável de ambiente `NETLENS_MASTER_KEY` | **Operacional / Fail-Closed** |
| `app/utils/sanitizer.py` | `SecretSanitizer` | Redação textual e estrutural recursiva profunda de tokens, senhas, communities e exceções. | `JobStore`, `JobEngine`, `ConfigService`, `ProvisionOrchestrator` | Regex pré-compiladas | `re`, `copy` | **Operacional e Sólido** |
| `app/analysis/ping_monitor.py` | `PingMonitor` | Coletor paralelo ICMP, detecção de intermitência e correlação entre control_plane e data_plane. | `app/__init__.py`, `app/routes/alerts.py` | `subprocess.run(ping)`, `ThreadPoolExecutor` | `config.json` | **Operacional**, mas dispara threads duplicadas em múltiplos workers. |
| `app/services/config_service.py` | `ConfigService` | Carregamento com fallbacks em cascata e persistência atômica (.tmp + fsync + os.replace). | Todos os serviços e rotas | `shutil`, `json`, `os` | `config.json`, `users.json`, `provision_plans.json` | **Alerta:** Contém senhas hardcoded em fallbacks (`@NetLensSecurePass2026!`). |
| `app/services/provision_drivers/netbox_provisioner.py` | `NetBoxProvisioner` | Driver de escrita REST no NetBox DCIM/Virtualization (Dispositivos, VMs, Interfaces, IPs). | `ProvisionOrchestrator.apply_plan` | `requests.post`, `requests.patch` | API NetBox v3+ | **Operacional** (Sem rollback em falhas intermediárias) |
| `app/services/provision_drivers/zabbix_provisioner.py` | `ZabbixProvisioner` | Driver JSON-RPC no Zabbix (Criação de Host, Interfaces SNMP/Agent, Macros). | `ProvisionOrchestrator.apply_plan` | `requests.post(api_jsonrpc.php)` | Zabbix API 6.x / 7.x | **Atenção:** Emite mutations em `REUSE` via `_ensure_snmp_interface`. |
| `app/services/provision_drivers/librenms_provisioner.py` | `LibreNMSProvisioner` | Driver REST API no LibreNMS (`/api/v0/devices`). | `ProvisionOrchestrator.apply_plan` | `requests.post`, `requests.patch` | LibreNMS REST API | **Operacional** |
| `app/services/provision_drivers/netdisco_provisioner.py` | `NetDiscoProvisioner` | Driver REST para disparar descoberta de topologia LLDP/CDP. | `ProvisionOrchestrator.apply_plan` | `requests.post` | NetDisco API | **Silent Fallback:** Retorna sempre `"status": "PASS"` mesmo quando ocorre Exception de rede. |
| `app/routes/intent_routes.py` & `intent_engine.py` | `VlanIntentEngine` | Segundo sistema de automação para switches de rede (Aruba, Comware, Dell, HP). | `/api/vlans/intent`, `/api/change-plans/*` | `NetworkDriverFactory`, `DeviceLockService` | SSH/CLI, Paramiko, Drivers | **Operacional mas Desconectado do JobEngine**: executa mutations síncronas em switches fora do pipeline do `JobEngine`. |

---

## 2. ARQUITETURA ATUAL (REAL vs DOCUMENTADA)

### 2.1. Reconstrução do Fluxo Real

```text
UI (templates/index.html)
     │
     ├── POST /api/v1/provision/plan
     │        ↓
     │   ProvisionOrchestrator.generate_plan
     │        ↓
     │   PolicyEngine -> DependencyEngine (Discovery Read-Only) -> IdempotencyEngine -> RiskEngine
     │        ↓
     │   Plan Hash (SHA-256) gerado e salvo em provision_plans.json (Status: PENDING_APPROVAL)
     │
     ├── POST /api/v1/provision/approve
     │        ↓
     │   ProvisionOrchestrator.approve_plan (Anti-Tamper: valida hash enviado vs calculado)
     │        ↓
     │   Status: APPROVED
     │
     ├── POST /api/v1/provision/apply
     │        ↓
     │   JobEngine.submit_plan_execution
     │        ↓
     │   JobStore.create_job_if_not_active (Lock fcntl em jobs.lock -> Previne Double-Apply)
     │        ↓
     │   InProcessExecutionBackend.submit (ThreadPoolExecutor assíncrono -> Retorna HTTP 202 com status QUEUED)
     │        ↓
     │   Worker Thread: JobStore.atomic_transition(QUEUED -> RUNNING)
     │        ↓
     │   ProvisionOrchestrator.apply_plan (Quad-Validation anti-tamper)
     │        ↓
     │   Provision Drivers (NetBox, Zabbix, LibreNMS, NetDisco)
     │        ↓
     │   ProvisionReconciliationEngine.verify_and_reconcile
     │        ↓
     │   JobStore: Status SUCCEEDED / FAILED
     │
     └── Polling: GET /api/v1/provision/jobs/<job_id>
```

### 2.2. Divergências Identificadas entre Arquitetura Documentada e Implementada

1. **Dualidade de Motores de Execução (Split-Architecture):**
   - *Documentado/Esperado:* Um único orquestrador e pipeline de automação corporativo no NetLens.
   - *Realidade no Código:* Existem **dois motores paralelos e não integrados**:
     - Motor A: `ProvisionOrchestrator` + `JobEngine` (para NetBox, Zabbix, LibreNMS, NetDisco) usando rotas `/api/v1/provision/*`.
     - Motor B: `VlanIntentEngine` + `ApplyExecutor` + `DeviceLockService` (para switches físicos Aruba, Dell, Comware, HP via SSH/CLI) usando rotas `/api/vlans/intent` e `/api/change-plans/*`.
   - *Impacto:* O `JobEngine` não tem visibilidade nem controle sobre as alterações em switches de rede executadas pelo `VlanIntentEngine`.

2. **Bypass Síncrono Legado (`/api/v1/provision/host`):**
   - *Localização:* `app/routes/provisioning.py:246-271`.
   - *Problema:* O endpoint `/api/v1/provision/host` executa um ciclo instantâneo `generate_plan -> approve_plan -> apply_plan -> verify_and_reconcile` de forma síncrona dentro da requisição HTTP, contornando completamente o `JobEngine`, `JobStore`, enfileiramento e locks anti-double-apply.

3. **Natureza da Reconciliação (Reconciliation Mirage):**
   - *Documentado:* "Compara DesiredState vs ObservedState em tempo real após a aplicação."
   - *Realidade no Código (`app/services/provision_reconciliation.py:127-133`):*
     ```python
     observed = ObservedState(
         netbox_status="PRESENT" if apply_results.get("netbox", {}).get("status") == "PASS" else "ABSENT",
         zabbix_status="PRESENT" if apply_results.get("zabbix", {}).get("status") == "PASS" else "ABSENT",
         ...
     )
     ```
     O motor de reconciliação **não consulta a telemetria ao vivo dos sistemas externos** no pós-apply; ele simplesmente lê o status retornado pelo driver de execução. Se o driver retornar `"PASS"`, a reconciliação assume estado `PRESENT`.

4. **Duplicação de Verificação no Frontend:**
   - O worker do `JobEngine` já executa `ProvisionReconciliationEngine.verify_and_reconcile` e armazena o resultado em `job.reconciliation` (`job_engine.py:102`).
   - O frontend (`templates/index.html:9279`), ao detectar status `SUCCEEDED`, ignora o resultado do job e faz uma segunda chamada explícita para `POST /api/v1/provision/verify`, executando a reconciliação uma segunda vez.

---

## 3. PROVISIONING END-TO-END (RASTREAMENTO DO FLUXO `POST /api/v1/provision/apply`)

### 3.1. Rastreamento Passo a Passo

1. **Entrada HTTP:**
   - **Arquivo:** `app/routes/provisioning.py`, Linha 180: `@provisioning_bp.route('/api/v1/provision/apply', methods=['POST'])`.
   - **Símbolo:** `apply_provision()`.
   - Recebe payload JSON `{ "plan_id": "PROV-2026-XXXX", "plan_hash": "..." }`.

2. **Validação de Entrada:**
   - **Arquivo:** `app/routes/provisioning.py`, Linhas 184-187.
   - Extrai `plan_id` e `plan_hash` (com fallback para `hash`). Se ausente, retorna HTTP 400.

3. **Submissão ao JobEngine:**
   - **Arquivo:** `app/routes/provisioning.py`, Linha 190.
   - Chama `JobEngine.submit_plan_execution(plan_id, config, plan_hash)`.

4. **Plan Lookup & Validação de Estado:**
   - **Arquivo:** `app/services/job_engine.py`, Linhas 47-56.
   - Chama `ProvisionOrchestrator.get_plan(plan_id)`.
   - Verifica se plano está em `("EXECUTING", "APPLIED", "COMMITTED")` -> Levanta `ValueError("CONCURRENT_EXECUTION_BLOCKED")`.
   - Verifica se `status != "APPROVED"` -> Levanta `ValueError("UNAPPROVED_PLAN")`.

5. **Validação do Hash do Plano:**
   - **Arquivo:** `app/services/job_engine.py`, Linhas 57-59.
   - Valida `calc_hash != plan_hash`. Se divergente, levanta `ValueError("TAMPER_DETECTED")`.

6. **Criação Atômica do Job no JobStore (Prevenção de Double Apply):**
   - **Arquivo:** `app/services/job_store.py`, Linhas 165-187.
   - **Símbolo:** `JobStore.create_job_if_not_active(plan_id, calc_hash)`.
   - Adquire `JobProcessFileLock` em `jobs.lock` (`fcntl.flock(LOCK_EX)`).
   - Recarrega `jobs.json`. Se existir job ativo (`QUEUED` ou `RUNNING`) com o mesmo `plan_id` e `plan_hash`, levanta `ValueError("CONCURRENT_EXECUTION_BLOCKED")`.
   - Cria novo `ProvisionJob(job_id=job_uuid, status=QUEUED)`.
   - Salva em `jobs.json` de forma atômica e libera o lock.

7. **Submissão ao Backend Assíncrono:**
   - **Arquivo:** `app/services/job_engine.py`, Linha 65.
   - Chama `cls._get_backend().submit(job.job_id, cls._run_job_worker, job.job_id, plan_id, config, calc_hash)`.
   - Retorna imediatamente HTTP 202 Accepted com `{ "success": true, "job_id": "...", "status": "QUEUED", "async": true }` (`routes/provisioning.py:199`).

8. **Inicialização do Worker em Background:**
   - **Arquivo:** `app/services/job_engine.py`, Linhas 70-87.
   - **Símbolo:** `_run_job_worker()`.
   - Chama `JobStore.atomic_transition(job_id, expected_statuses=["QUEUED"], new_status="RUNNING")`.
   - Sob `JobProcessFileLock`, atualiza `job.started_at` e `job.worker_id`.

9. **Execução no ProvisionOrchestrator:**
   - **Arquivo:** `app/services/provision_orchestrator.py`, Linhas 346-388.
   - **Símbolo:** `ProvisionOrchestrator.apply_plan(plan_id, config, plan_hash)`.
   - **Quad-Validation:**
     - Status deve ser `APPROVED` (Linha 361).
     - Hash recalculado das operações deve ser idêntico ao `plan["hash"]` e `plan["approved_plan_hash"]` (Linhas 374-377).
     - Hash do argumento deve bater com `plan["hash"]` (Linhas 379-380).
     - Risco não pode ser `CRITICAL` (Linhas 382-384).
   - Transita plano para `status = "EXECUTING"` e persiste sob `ProcessFileLock`.

10. **Dispatch para Drivers de Provisionamento:**
    - **Arquivo:** `app/services/provision_orchestrator.py`, Linhas 398-423.
    - Executa em ordem sequencial:
      - `NetBoxProvisioner.provision(...)`
      - `ZabbixProvisioner.provision(...)`
      - `LibreNMSProvisioner.provision(...)`
      - `NetDiscoProvisioner.provision(...)`

11. **Finalização do Plano no Orchestrator:**
    - **Arquivo:** `app/services/provision_orchestrator.py`, Linhas 425-430.
    - Atualiza `plan["status"] = "APPLIED"`, `plan["applied_at"]`, `plan["execution_results"] = results`.
    - Persiste em `provision_plans.json`.

12. **Reconciliação e Sanitização de Saída:**
    - **Arquivo:** `app/services/job_engine.py`, Linhas 95-104.
    - Sanitiza resultados com `SecretSanitizer.sanitize_dict()`.
    - Executa `ProvisionReconciliationEngine.verify_and_reconcile()`.

13. **Conclusão e Persistência do Job:**
    - **Arquivo:** `app/services/job_engine.py`, Linhas 108-113.
    - Atualiza `job.status = SUCCEEDED`, `job.finished_at`, anexa resultados sanitizados.
    - Salva via `JobStore.save_job(job)`.

### 3.2. Análise de Fragilidades no Pipeline

- **Pontos de Bloqueio:** O worker executa chamadas HTTP síncronas a 4 sistemas externos (`timeout` total somado de até 15s por job). Se um sistema travar sem responder dentro do timeout, o worker da thread fica bloqueado.
- **Pontos de Race Condition:** Em `ProvisionOrchestrator`, a persistência do `_PLAN_STORE` pode sobrescrever planos criados por outros workers (detalhado na Seção 4).
- **Pontos de Retry:** **NÃO EXISTEM RETRIES** automáticos nos drivers (`NetBoxProvisioner`, `ZabbixProvisioner`, `LibreNMSProvisioner`). Se houver falha de rede temporária em um POST, a operação falha imediatamente.
- **Pontos de Rollback:** **NÃO EXISTE ROLLBACK**. Se o NetBox criar a VM com sucesso, mas o Zabbix falhar ao criar o Host, a VM permanece criada no NetBox e o Zabbix fica órfão. O estado do sistema externo fica parcialmente aplicado.

---

## 4. CONCORRÊNCIA E MULTIPROCESSO

### 4.1. Auditoria dos Mecanismos de Lock e Persistência

| Componente | Mecanismo de Concorrência | Arquivo de Lock | Multi-Thread | Multi-Processo (Gunicorn) | Avaliação Crítica |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **JobStore** | `JobProcessFileLock` (`fcntl.flock`) | `jobs.lock` | Seguro | Seguro | **Correto e Robusto.** Utiliza read-check-modify-write estrito dentro de um lock de arquivo exclusivo no sistema operacional. |
| **ProvisionOrchestrator** | `_PLAN_LOCK` (`threading.Lock`) + `ProcessFileLock` | `provision_plans.lock` | Seguro em single process | **VULNERÁVEL A SOBRESCRITA** | **Grave Race Condition:** O dicionário `_PLAN_STORE` reside na memória do módulo. O método `generate_plan()` **não recarrega do disco** antes de salvar. Se Worker A e Worker B gerarem planos simultaneamente, o último a salvar sobrescreve o arquivo `provision_plans.json` com seu próprio cache de memória, apagando os planos do outro worker. |
| **InProcessExecutionBackend** | `threading.Lock` + `ThreadPoolExecutor` | N/A (In-Memory) | Seguro | **Process-Isolated** | Se o Gunicorn estiver configurado com múltiplos workers (`-w 4`), cada worker tem seu próprio pool de threads. Um worker não tem acesso nem conhecimento das threads em execução no outro worker. |
| **DeviceLockService** | `threading.Lock` + Heartbeat Thread | N/A (In-Memory) | Seguro em single process | **Não funciona em multiprocesso** | O lock de switches físicos para VLANs (`app/services/lock_service.py`) é 100% em memória. Dois workers Gunicorn podem travar o mesmo switch simultaneamente. |

### 4.2. Cenários de Falha e Comportamento

1. **Double Apply Concorrente:**
   - *Comportamento:* Testado e protegido no `JobStore.create_job_if_not_active()`. Se duas requisições simultâneas tentarem aplicar o mesmo `plan_id` + `plan_hash`, uma delas obtém o lock de arquivo primeiro e cria o job; a segunda falha com HTTP 409 `CONCURRENT_EXECUTION_BLOCKED`.

2. **Crash durante estado QUEUED ou RUNNING:**
   - *Comportamento:* Ao reiniciar a aplicação, `create_app()` chama `JobEngine.recover()`.
   - Sob `JobProcessFileLock`, qualquer job que tenha permanecido em `QUEUED` ou `RUNNING` é atômica e imediatamente transitado para `FAILED` com `failure_code = "EXECUTION_INTERRUPTED_BY_RESTART"`.

3. **Inconsistência de Polling entre Múltiplos Workers:**
   - O cliente recebe `job_id` do Worker A e faz polling em `GET /api/v1/provision/jobs/<job_id>`.
   - Se a requisição cair no Worker B, o Worker B lê diretamente do arquivo `jobs.json` protegido por lock. Logo, o polling **funciona corretamente** mesmo entre múltiplos workers.

---

## 5. SEGURANÇA E HIGIENE DE CREDENCIAIS

### 5.1. Vazamento Crítico de Credenciais Hardcoded no Código

A execução dos testes de higiene (`test_sprint_10_11_0_hygiene.py`) revelou uma falha de segurança severa: **a senha de produção dos firewalls e switches corporativos (`@NetLensSecurePass2026!`) está em texto claro no repositório**:

1. **`app/services/config_service.py` (Linhas 148, 161, 174, 187):**
   - Senha padrão inserida nos dicionários de fallback dos firewalls:
     - `fw-matriz-sp` (10.1.1.2)
     - `fw-brasilia` (10.61.0.250)
     - `fw-praca-10-65` (10.65.0.250)
     - `fw-str` (10.11.0.253)
2. **`app/services/sophos_service.py` (Linhas 66, 79, 92, 105, 114):**
   - Senha idêntica repetida em fallbacks estáticos de `SophosService.get_appliances()` e `os.environ.get("SOPHOS_API_PASS", "@NetLensSecurePass2026!")`.
3. **`app/routes/inventory.py` (Linha 67):**
   - `"password": data.get('password') or '@NetLensSecurePass2026!'`.
4. **`templates/index.html` (Linha 12994):**
   - **Vazamento para o navegador do cliente:**
     `password: useDef ? '@NetLensSecurePass2026!' : password`
     Qualquer usuário que abra o código-fonte da página HTML no navegador tem acesso à credencial de administrador dos firewalls corporativos.
5. **Scripts de Deploy em `scratch/`:**
   - `scratch/deploy_netlens.py` (Linha 33): `password = "NetLensSecurePass2026!"`.
   - `scratch/deploy_sprint_10_9_0_remote.py` (Linha 9 e 12):
     `PASSWORD = "NetLensSecurePass2026!"`
     `MASTER_KEY = "y1Z4pQ8wR2tV5xY8zA1bC3dE5fG7hI9jK0lM2nO4pQ6="` (A chave mestra Fernet de produção está em texto claro no script!).

### 5.2. Vazamento de Credenciais via APIs REST

1. **Exposição de Senhas de Banco de Dados (`app/routes/admin.py:925-935`):**
   ```python
   @admin_bp.route('/api/settings/db', methods=['GET'])
   def get_db_settings():
       config = ConfigService.load_config()
       dbs = config.get("databases", {})
       return jsonify({
           "netdisco": dbs.get("netdisco", {}),
           "librenms": dbs.get("librenms", {}),
           "zabbix": dbs.get("zabbix", {})
       })
   ```
   *Problema:* O código possui um comentário dizendo que sanitiza as senhas, mas **retorna o dicionário cru sem nenhuma sanitização**. As senhas dos bancos de dados Netdisco, LibreNMS e Zabbix são enviadas em texto claro via JSON para o frontend.

2. **Exposição de Senhas de Firewalls (`app/routes/inventory.py:47`):**
   - A rota `GET /api/firewall/appliances` retorna o resultado de `SophosService.get_appliances()`, que inclui o campo `"password": "@NetLensSecurePass2026!"` sem máscara ou exclusão.

### 5.3. Avaliação do `SecretService` e `SecretSanitizer`

- **`SecretService` (`app/services/secret_service.py`):**
  - Criptografia com Fernet (`FERNET:<token>`).
  - **Comportamento Fail-Closed:** Se `NETLENS_MASTER_KEY` não estiver definida no ambiente, `get_fernet()` levanta `ConfigurationError` imediato, impedindo sobrescrever ou corromper segredos existentes.
- **`SecretSanitizer` (`app/utils/sanitizer.py`):**
  - Implementa redação de chaves sensíveis (`snmp_community`, `password`, `token`, etc.) e padrões de regex.
  - Funciona perfeitamente nos módulos em que é acionado (`JobStore`, `job_engine.py`). No entanto, **rotas legadas e endpoints de administração não invocam o `SecretSanitizer`**, criando caminhos de bypass.

---

## 6. CONFIGURAÇÃO E COMPORTAMENTO FAIL-CLOSED

### 6.1. Matriz de Comportamento dos Consumidores de Configuração

| Componente / Integração | Fonte Primária | Fallback / Default | Classificação | Avaliação Detalhada |
| :--- | :--- | :--- | :--- | :--- |
| **Zabbix API** | `config.json -> zabbix` | `NETLENS_ZABBIX_*` env vars / user "admin", pass "SUA_SENHA_AQUI" | **SILENT FALLBACK / FAIL-OPEN** | Se não conseguir conectar à API ao vivo, usa templates hardcoded (`app/routes/provisioning.py:100-111`). |
| **NetBox API** | `config.json -> netbox` | Lista estática de 19 clusters Proxmox hardcoded (`provisioning.py:43-61`) | **SILENT FALLBACK** | Se a URL do NetBox estiver inacessível, retorna clusters fixos fingindo sucesso. |
| **LibreNMS API** | `config.json -> librenms` | `NETLENS_LIBRENMS_*` env vars / vazio | **FAIL-CLOSED** | Levanta erro e retorna status FAIL no provisioner. |
| **NetDisco API** | `config.json -> netdisco` | `NETLENS_NETDISCO_*` env vars / vazio | **FAIL-OPEN / SILENT** | Retorna `"status": "PASS"` mesmo quando ocorre falha de conexão HTTP. |
| **Ping Targets** | `config.json -> ping_targets` | Vazio `{}` | **BLOCK / FAIL-CLOSED** | Não dispara pings; retorna alertas vazios sem derrubar a aplicação. |
| **Switches Dell** | `config.json -> dell_switches` | Vazio `[]` | **FAIL-CLOSED** | Se lista vazia, rota `/api/dell-alignment/validate` retorna HTTP 400. |
| **Firewalls Sophos** | `config.json -> firewalls` | 4 firewalls hardcoded (10.1.1.2, 10.61.0.250, 10.65.0.250, 10.11.0.253) | **SILENT FALLBACK** | Se `config.json` estiver sem firewalls, assume os 4 firewalls hardcoded com senha default. |

---

## 7. AUDITORIA PROFUNDA DE DRIVERS E PROVISIONERS

### 7.1. Drivers de Provisionamento de Infraestrutura (`app/services/provision_drivers/`)

1. **`NetBoxProvisioner` (`netbox_provisioner.py`):**
   - *Capabilities:* Criação de Devices (físicos), VMs (virtualization), Interfaces, Alocação de IP e atribuição de IP primário.
   - *Modo de Operação:* Read-only em `action="REUSE"`; Write em `action="CREATE"`.
   - *Timeout:* 4 segundos por requisição.
   - *Retry:* Nenhum.
   - *Rollback:* Inexistente (falha na alocação do IP deixa o dispositivo criado órfão no NetBox).
   - *Validação SSL:* `verify=False` forçado.

2. **`ZabbixProvisioner` (`zabbix_provisioner.py`):**
   - *Capabilities:* Login JSON-RPC, criação de Host, atribuição de grupos, templates, interfaces SNMP (porta 161) e Agent (porta 10050), configuração de macro `{$SNMP_COMMUNITY}`.
   - *Vulnerabilidade Crítica de Mutação em REUSE:*
     Na Linha 39 (`ZabbixProvisioner._ensure_snmp_interface`), mesmo quando `action == "REUSE"`, o driver executa chamadas de escrita (`hostinterface.create` e `usermacro.create`) para alterar o equipamento no Zabbix sem aprovação explícita para essa mutação.
   - *Timeout:* 3s a 4s por requisição.
   - *Retry:* Nenhum.

3. **`LibreNMSProvisioner` (`librenms_provisioner.py`):**
   - *Capabilities:* Cadastro de dispositivo SNMP (`/api/v0/devices`) e patch de `sysName`.
   - *Modo:* `action == "REUSE"` retorna `PASS` imediato sem chamadas de rede.
   - *Timeout:* 4s / 3s.

4. **`NetDiscoProvisioner` (`netdisco_provisioner.py`):**
   - *Capabilities:* Envio de requisição de descoberta de topologia (`/api/v1/search/device`).
   - *Comportamento Anômalo:* Qualquer exceção capturada é mascarada e retorna `"status": "PASS"`.

### 7.2. Drivers de Equipamentos de Rede (Switches Físicos) (`app/drivers/`)

- Suporte a múltiplos vendors: Aruba/ProCurve, HP Comware, Dell OS9, HP Stanton, 3Com.
- Transporte via SSH (`paramiko`) com comandos diretos CLI.
- **Risco Operacional:**
  O endpoint `/api/backup-config` (`app/routes/dell.py:10-35`) e `/api/dell-alignment/validate` disparam conexões SSH diretas com credenciais enviadas pelo usuário, sem passar pelo pipeline de aprovação do `ProvisionOrchestrator` ou `JobEngine`.

---

## 8. FRONTEND E CONTRATO DE API

### 8.1. Auditoria do Contrato do Frontend (`templates/index.html`)

1. **Ciclo de Aplicação e Polling:**
   - O frontend submete `POST /api/v1/provision/apply` com `{ plan_id, plan_hash }`.
   - Trata status HTTP 202 com sucesso, obtém `data.job_id`, e entra em polling a cada 1000ms em `GET /api/v1/provision/jobs/${jobId}` (`templates/index.html:9253-9272`).
   - Finaliza o polling com sucesso quando status é `SUCCEEDED` ou erro quando `FAILED`/`CANCELLED`.
   - **Divergência Contratual:** O frontend não chama `GET /api/v1/provision/jobs/${jobId}/result`. Em vez disso, chama diretamente `POST /api/v1/provision/verify`.

2. **Incompatibilidade Contratual em `/api/links`:**
   - O teste de regressão `test_ui_regression_recovery.py:22` falha porque o backend agora responde `{"links": [...], "success": True}`, enquanto clientes/testes antigos esperavam uma lista JSON crua (`[...]`).

3. **Resiliência a Métricas no PingMonitor:**
   - O frontend utiliza formatadores seguros com fallback (`(val || 0).toFixed(2)`), evitando os erros de `undefined% Perda` auditados e sanados no Sprint 10.12.1.

---

## 9. PINGMONITOR (ANÁLISE DE CONCORRÊNCIA E THREADING)

### 9.1. Fluxo de Execução

```text
config.json -> ConfigService.load_config() -> ping_targets
     ↓
PingMonitor.__init__() (executa _ping_all inicial síncrono)
     ↓
PingMonitor.start() (dispara thread daemon _loop)
     ↓
_ping_all() -> ThreadPoolExecutor(max_workers=len(ips))
     ↓
subprocess.run(["ping", ...]) por IP
     ↓
_analyze_intermittency() (avalia médias dos últimos 5 ticks)
     ↓
Gera alertas de Control Plane vs Data Plane
```

### 9.2. Problemas Críticos Auditados

1. **Múltiplas Instâncias Concorrentes sob Servidores WSGI (Gunicorn):**
   - O objeto `ping_monitor` é instanciado na importação de `app/routes/alerts.py:21`.
   - Dentro de `app/__init__.py:53`, é executado `ping_monitor.start()`.
   - Se o Gunicorn for executado com 4 workers (`-w 4`), **4 processos filhos independentes criam 4 instâncias separadas do `PingMonitor`**. Cada uma inicia sua própria thread em segundo plano, disparando pings redundantes a cada 3 segundos contra a infraestrutura de rede.
   - Além disso, o histórico de latência e perda (`self.history`) fica fragmentado na memória de cada processo. Se uma requisição do frontend consultar o Worker A e a seguinte o Worker B, os gráficos e dados de latência exibirão variações e descontinuidades artificiais.

2. **Aliases Legados Hardcoded no Código:**
   - Em `app/analysis/ping_monitor.py:198-201`, existem IPs e nomes de dispositivos hardcoded para manter compatibilidade com dashboards legados:
     ```python
     "dell_mgmt_loss": round(loss_stats.get("10.11.0.249", avg_cp_loss), 2),
     "dell_ptp_loss": round(loss_stats.get("10.1.1.1", avg_cp_loss), 2),
     "sophos_loss": round(loss_stats.get("10.1.1.2", avg_dp_loss), 2),
     "dell_eth_loss": round(loss_stats.get("10.11.0.248", avg_dp_loss), 2)
     ```

---

## 10. TESTES E BASELINE REAL

### 10.1. Execução do Baseline Atual (Read-Only)

A execução da suíte completa de testes locais revelou o seguinte baseline REAL:

```text
TOTAL DE TESTES: 288
PASS:            285
FAIL:            3
ERROR:           0
SKIPPED:         0
TEMPO:           26.999s
```

### 10.2. Diagnóstico Completo das 3 Falhas

1. **`test_sprint_10_11_0_hygiene.py:TestSprint10110Hygiene.test_1_zero_hardcoded_credentials_in_source`**
   - **Falha:** `AssertionError: 4 != 0 : Credentials found in source: ['.../inventory.py', '.../sophos_service.py', '.../config_service.py', '.../index.html']`
   - **Causa Real:** O padrão de senha corporativa `@NetLensSecurePass2026!` foi reintroduzido nos arquivos de inventário, serviço sophos, serviço de configuração e no template HTML.

2. **`test_ui_regression_recovery.py:TestUIRegressionRecovery.test_links_endpoint_contains_all_four_systems`**
   - **Falha:** `AssertionError: {'links': [...], 'success': True} is not an instance of <class 'list'>`
   - **Causa Real:** A rota `/api/links` foi modernizada para retornar um dicionário padronizado com flag de sucesso (`{"links": [...], "success": True}`), mas o teste de regressão antigo continuou esperando um retorno de lista crua.

3. **`test_wan_monitor_service.py:TestWanMonitorService.test_get_wan_health_aggregation`**
   - **Falha:** `AssertionError: 10 != 7`
   - **Causa Real:** A lista base `WanMonitorService.WAN_LINKS` possui 7 links estáticos. No entanto, foram cadastrados 3 links adicionais dinâmicos no ambiente, totalizando 10 links no sumário agregado. O teste faz uma asserção rígida comparando o total com a lista estática original.

### 10.3. Classificação dos Testes por Categoria

| Categoria | Arquivos de Teste | Quantidade de Testes | Qualidade / Cobertura |
| :--- | :--- | :--- | :--- |
| **Unitários (Models/Engines)** | `test_provision_policy_engine.py`, `test_provision_idempotency_engine.py`, `test_provision_risk_engine.py`, `test_provision_dependency_engine.py` | 17 | **Alta.** Cobertura determinística com asserções rigorosas sem mocks de rede. |
| **Segurança & Criptografia** | `test_sprint_10_9_0_security_hardening.py`, `test_sprint_10_11_0_hygiene.py` | 8 | **Excelente.** Testa Fernet, canary secrets, injeção de Master Key e detecção de segredos em código. |
| **Concorrência & Lifecycle** | `test_sprint_10_10_0_job_engine.py`, `test_sprint_10_12_0_refactor.py` | 12 | **Alta.** Usa `multiprocessing.Process` real para validar corrida entre processos e lock de arquivo. |
| **API & Contratos REST** | `test_provision_ui_contract.py`, `test_sprint_10_8_0_provisioning_hardening.py`, `test_admin_servers.py`, `test_dynamic_firewalls.py` | 18 | **Média.** Depende fortemente de mocks de rede e estruturas JSON em memória. |
| **Integração de Features** | `test_sprint_10_13_0_features.py` | 23 | **Alta.** Valida novas capacidades do Zabbix SNMP e CRUD de administração. |
| **Monitoramento & Análise** | `test_port_events_stp_flapping.py`, `test_bottlenecks_and_errors.py`, `test_traffic_and_host_search.py`, `test_wan_monitor_service.py` | 40 | **Média.** Alguns testes contêm asserções rígidas sobre volumes dinâmicos de dados. |
| **Regressão / Legado** | `test_app.py`, `test_ui_regression_recovery.py` | 139 | **Heterogênea.** Contém testes legados que usam contratos de API antigos. |

---

## 11. HISTÓRICO E LINHA DO TEMPO DAS SPRINTS

| Sprint | Escopo Declarado nos Relatórios | O que o Código Atual Realmente Faz | Divergências / Conclusão |
| :--- | :--- | :--- | :--- |
| **10.7.x** | Introdução do Pipeline de Provisionamento: Policy Engine, Dependency Discovery, Idempotency e Risk. | Implementado em `app/policies/` e `app/services/provision_*`. | Totalmente coerente. O cálculo de Hash SHA-256 e detecção de tamper estão ativos. |
| **10.8.0** | Persistência do Plan Store, ofuscação inicial de credenciais (ENC:b64), Quad-Validation. | Implementado em `provision_orchestrator.py`. | Coerente, mas persistência de planos em memória estática (`_PLAN_STORE`) revelou fragilidade multi-processo. |
| **10.9.0** | Segurança de segredos: Fernet (`FERNET:`), obrigatoriedade de `NETLENS_MASTER_KEY`, ProcessFileLock. | `SecretService` implementado com fail-closed estrito. | Coerente no backend, mas scripts em `scratch/` mantiveram a master key hardcoded. |
| **10.10.0** | Job Engine Assíncrono: desacoplamento de requisições HTTP, ciclo de vida QUEUED->RUNNING->SUCCEEDED, startup crash recovery. | `JobEngine`, `JobStore`, `InProcessExecutionBackend` totalmente operacionais. | Coerente e robusto com locks atômicos no `JobStore`. |
| **10.11.0** | Higiene de Código: eliminação total de senhas e caminhos efêmeros (.gemini) no repositório. | Teste falha atualmente. | **DIVERGÊNCIA:** Senhas foram reintroduzidas no código em sprints posteriores (10.12/10.13). |
| **10.12.0** | Refatoração de concorrência anti-TOCTOU, retorno estrito de HTTP 202 Accepted no Apply, eliminação de IPs hardcoded. | `JobStore.atomic_transition` e HTTP 202 ativos. | Coerente quanto ao Job Engine, mas ainda restam fallbacks com IPs no `ConfigService`. |
| **10.12.1** | Remediação: resiliência do PingMonitor a listas vazias e aliases de compatibilidade de métricas no frontend. | Implementado em `ping_monitor.py` e `index.html`. | Coerente. O PingMonitor não trava mais com `ping_targets` vazio. |
| **10.13.0** | Suporte avançado a SNMP v2c no Zabbix (macro `{$SNMP_COMMUNITY}`), CRUD de administração para sites, modelos e perfis, campos de VM no NetBox. | Implementado e verificado por 23 testes passando em `test_sprint_10_13_0_features.py`. | Coerente e ativo. |

---

## 12. OPERAÇÕES EM PRODUÇÃO

> [!IMPORTANT]
> **DIRETRIZ 100% READ-ONLY RESPEITADA:**  
> - Nenhum switch de rede, roteador ou firewall foi contactado via SSH ou SNMP SET.
> - Nenhum serviço de produção foi reiniciado.
> - Nenhuma operação de deploy ou escrita em disco remoto foi disparada.
> - Todas as validações foram realizadas por análise estática e execução de testes em ambiente de sandbox isolado.

As seguintes operações e funcionalidades existentes no código **EXIGEM VALIDAÇÃO CONTROLADA EM PRODUÇÃO** com janelas de manutenção formalmente aprovadas:

1. `REQUIRES PRODUCTION VALIDATION`: Aplicação real de interfaces SNMP em hosts existentes no Zabbix (`ZabbixProvisioner._ensure_snmp_interface`).
2. `REQUIRES PRODUCTION VALIDATION`: Criação de interfaces virtuais e alocação de IPs no NetBox v3+ em cluster Proxmox de produção.
3. `REQUIRES PRODUCTION VALIDATION`: Execução do motor de VLAN Intent em switches core Dell OS9 e HP Comware via `VlanIntentEngine.apply_plan`.

---

## 13. MATRIZ DE RISCO ARQUITETURAL

| ID | Severidade | Componente | Arquivo : Linha | Símbolo | Problema | Evidência | Impacto | Risco | Recomendação |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R-01** | **CRITICAL** | Frontend / Auth | `templates/index.html:12994` | JS Inline | Senha corporativa de firewalls exposta em texto claro no frontend | `password: useDef ? '@NetLensSecurePass2026!' : password` | Comprometimento total da segurança de perímetro por qualquer usuário da UI | **CRÍTICO** | Remover imediatamente o valor do HTML; buscar via backend sob autenticação. |
| **R-02** | **CRITICAL** | Admin Routes | `app/routes/admin.py:925-935` | `get_db_settings` | Exposição de credenciais de bancos de dados via API REST sem sanitização | Retorna `dbs.get(...)` cru com senhas em texto puro | Vazamento de credenciais de bancos Netdisco, LibreNMS e Zabbix | **CRÍTICO** | Aplicar máscara estrutural substituindo senhas por `[CONFIGURED]` no GET. |
| **R-03** | **HIGH** | ConfigService / Sophos | `app/services/config_service.py:148` | `load_config` | Senhas de produção hardcoded como fallbacks no backend | Senha `@NetLensSecurePass2026!` em 4 firewalls de fallback | Falha no teste de higiene e vazamento em logs | **ALTO** | Substituir por leitura obrigatória de variáveis de ambiente sem senha padrão. |
| **R-04** | **HIGH** | ProvisionOrchestrator | `app/services/provision_orchestrator.py:286` | `generate_plan` | Sobrescrita de planos entre workers em multi-processo (Gunicorn) | `_PLAN_STORE` em memória não recarrega do disco antes de persistir novo plano | Perda silenciosa de planos gerados em outros workers | **ALTO** | Migrar `_PLAN_STORE` para padrão idêntico ao `JobStore` com recarga e lock de arquivo estrito. |
| **R-05** | **HIGH** | ZabbixProvisioner | `app/services/provision_drivers/zabbix_provisioner.py:150` | `_ensure_snmp_interface` | Operação de escrita não declarada disparada em plano marcado como `REUSE` | Chama `hostinterface.create` e `usermacro.create` sob `action="REUSE"` | Alteração inesperada e não aprovada na configuração do host no Zabbix | **ALTO** | Declarar a criação da interface como operação explícita no plano durante o Generate Plan. |
| **R-06** | **HIGH** | PingMonitor | `app/analysis/ping_monitor.py:217` | `start` | Múltiplas instâncias de monitoramento e loops de ping sob múltiplos workers | Instanciado e iniciado em cada worker do Gunicorn na carga de `create_app()` | Tráfego ICMP multiplicado por N workers; métricas de latência inconsistentes na UI | **ALTO** | Isolar o PingMonitor em um processo/daemon dedicado ou iniciar apenas sob processo master. |
| **R-07** | **MEDIUM** | Provisioning Route | `app/routes/provisioning.py:246` | `legacy_provision_host` | Endpoint de bypass do JobEngine executando apply síncrono | Rota `/api/v1/provision/host` chama `apply_plan` diretamente | Bypassa fila assíncrona, rastreamento de jobs e crash recovery | **MÉDIO** | Descontinuar ou redirecionar o endpoint para submeter ao `JobEngine`. |
| **R-08** | **MEDIUM** | NetDiscoProvisioner | `app/services/provision_drivers/netdisco_provisioner.py:28` | `provision` | Silent Fallback mascarando exceções de conexão como sucesso | Retorna `"status": "PASS"` no bloco `except Exception` | Falsa sensação de sucesso em relatórios de auditoria | **MÉDIO** | Retornar `"status": "FAIL"` e propagar a causa real do erro. |
| **R-09** | **MEDIUM** | Dual Automation Engines | `app/services/intent_engine.py` vs `provision_orchestrator.py` | Arquitetura | Dois motores de mudança paralelos e desconectados | VLAN Intent aplica em switches via SSH; Orchestrator aplica em NetBox/Zabbix | Falta de governança centralizada sobre mudanças físicas na rede | **MÉDIO** | Unificar o pipeline de execução sob o `JobEngine`. |
| **R-10** | **LOW** | Deployment Scripts | `scratch/deploy_sprint_10_9_0_remote.py:12` | `MASTER_KEY` | Chave mestra Fernet de produção gravada em script em disco | `MASTER_KEY = "y1Z4..."` em texto claro | Comprometimento da chave de criptografia de planos em repouso | **BAIXO** | Purgar scripts com segredos de `scratch/` e utilizar cofre de senhas. |

---

## 14. ACHADOS ARQUITETURAIS ESTRUTURAIS

1. **Limitações da Persistência em Arquivos JSON:**
   - O NetLens utiliza atualmente arquivos JSON em disco (`config.json`, `jobs.json`, `provision_plans.json`, `users.json`, `audit_log.json`).
   - Embora o `JobStore` tenha atingido um grau admirável de maturidade com escrita em `.tmp`, `fsync` de arquivo e diretório, e substituição atômica via `os.replace` sob `fcntl.flock`, esse modelo impõe sérias restrições de escalabilidade:
     - Impossibilidade de consultas relacionais, joins e filtros eficientes à medida que o histórico de jobs e planos cresce.
     - Overhead de I/O em que o arquivo inteiro precisa ser serializado e desserializado a cada pequena atualização de status.
     - **Recomendação Estratégica:** A implantação futura de um banco de dados relacional (PostgreSQL), conforme já cogitado pelo time, será o passo definitivo para suportar relatórios avançados de links WAN, histórico de telemetria e integridade transacional ACID.

2. **Backend de Execução em Memória (`InProcessExecutionBackend`):**
   - O uso de `ThreadPoolExecutor` local elimina a necessidade imediata de infraestruturas complexas como Celery e Redis. No entanto, se o processo do worker for finalizado ou sofrer crash, as tarefas em voo são abortadas e dependem exclusivamente da heurística do `JobEngine.recover()` na próxima inicialização do sistema.

3. **Arquitetura de Reconciliação Declarativa vs Reativa:**
   - A reconciliação atual analisa o relatório de execução dos drivers, e não o estado real observado via novas sondagens pós-aplicação. Um motor de reconciliação maduro deve disparar uma re-consulta independente nos sistemas após a conclusão do job para aferir a presença real dos objetos.

---

## 15. CONCLUSÃO E PARECER DO AUDITOR

### 15.1. Respostas aos Questionamentos Arquiteturais

- **A arquitetura atual está coerente com o desenho pretendido?**  
  *Sim, em grande parte.* O pipeline determinístico de provisionamento (Policy Engine, Dependency Discovery, Idempotency, Risk Assessment, Hash SHA-256 e JobEngine assíncrono com retorno HTTP 202) está rigorosamente implementado e sustentado por 285 testes unitários e de integração ativos.
- **Quais partes estão comprovadamente sólidas?**  
  - O motor de ciclo de vida assíncrono `JobEngine` e o armazenamento seguro `JobStore` (protegido contra double-apply, com atomic_transition e crash recovery).
  - O pipeline determinístico de cálculo de Hash SHA-256 e validação anti-tamper.
  - O sistema de sanitização estrutural `SecretSanitizer`.
  - A suíte de testes de concorrência com processos reais.
- **Quais partes precisam de validação e correção imediata?**  
  - **Segurança de Credenciais:** Eliminação das senhas corporativas e da `NETLENS_MASTER_KEY` presentes no frontend, rotas de admin e scripts de scratch.
  - **Concorrência do Orchestrator:** O `_PLAN_STORE` precisa abandonar o cache de memória estática e adotar o mesmo padrão atômico do `JobStore`.
  - **PingMonitor em Multi-Worker:** O monitor de latência precisa de proteção contra execução concorrente duplicada sob servidores WSGI como Gunicorn.
- **Existem caminhos que bypassam as barreiras de controle?**  
  - Sim: o endpoint `/api/v1/provision/host` (execução síncrona sem Job) e a rota legada `/api/vlans/intent` (execução de comandos CLI em switches fora do pipeline do JobEngine).
- **Perímetro de CODE FREEZE Recomendado:**  
  Recomenda-se estritamente o congelamento (`CODE FREEZE`) dos seguintes módulos centrais até a auditoria externa:
  - `app/services/job_engine.py`
  - `app/services/job_store.py`
  - `app/services/secret_service.py`
  - `app/utils/sanitizer.py`
  - `app/policies/provision_policy_engine.py`
  - `app/models/provision_*.py`

---

## 16. ARTEFATO FINAL E MÉTRICAS DE EXECUÇÃO

Em conformidade estrita com o mandato diagnóstico e read-only da auditoria:

```text
CODE_MODIFICATIONS = 0
NETWORK_MUTATIONS = 0
PRODUCTION_CHANGES = 0
```

ABSOLUTE STOP — AUDITORIA CONCLUÍDA. NÃO MODIFIQUE NENHUM ARQUIVO. NÃO FAÇA DEPLOY. AGUARDE A ANÁLISE DO ARQUITETO.
