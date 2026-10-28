# NETLENS — SPRINT 10.9.0 IMPLEMENTATION PLAN (REFINED)
## SECURITY HARDENING & ATOMIC PLAN STORE

This refined implementation plan incorporates all 10 mandatory architectural gates for **Sprint 10.9.0: Security Hardening & Atomic Plan Store**, focusing on real Fernet cryptographic secret protection at rest, atomic file persistence with directory `fsync()`, structural/textual exception sanitization, multi-process `fcntl.flock` state transition locking, and aggressive leakage testing.

---

## User Review Required

> [!IMPORTANT]
> **CODE FREEZE ON MULTIVENDOR DRIVERS**:
> No changes will be made to any vendor driver (`DellDriver`, `CiscoDriver`, `ArubaDriver`, `HPEComwareDriver`, etc.). All tests operate strictly in read-only preflight or mocked driver environments. Zero physical switch mutations or external platform writes will occur.

> [!CAUTION]
> **MANDATORY `NETLENS_MASTER_KEY` (NO SILENT CRYPTOGRAPHIC FALLBACK)**:
> Encryption/decryption of persisted secrets requires `NETLENS_MASTER_KEY`. If not configured, the system will **not** generate a silent fallback key or overwrite existing plans. Operations requiring encrypted secret access will raise an explicit operational error, preventing plan corruption across server reboots/redeployments.

> [!IMPORTANT]
> **TWO-PHASE DEPLOYMENT**:
> Phase 1 is strictly local implementation, test verification (177 baseline + 10.9.0 tests PASS), and security audit. Phase 2 (remote sync to `192.168.10.51`) will **only** occur after explicit user approval.

---

## Proposed Changes

### 1. Secret Management & Cryptography Component

#### [NEW] [secret_service.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/secret_service.py)
- Implement `SecretService` class utilizing `cryptography.fernet.Fernet`.
- Implement `get_master_key()` reading `NETLENS_MASTER_KEY` from `os.environ`. If absent, raise an explicit operational `ConfigurationError` rather than generating a silent machine-bound key.
- Implement `encrypt_secret(secret_str: str) -> str` returning `FERNET:<token>`.
- Implement `decrypt_secret(enc_str: str) -> str`:
  - Recognizes `FERNET:<token>` and decrypts using `Fernet`.
  - Recognizes legacy `ENC:<base64>` in **READ-ONLY / LEGACY** mode for in-memory decoding. On next save, payload is persisted strictly as `FERNET:<token>`. Logs a migration warning.

### 2. Centralized Structural & Textual Sanitization Component

#### [NEW] [sanitizer.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/utils/sanitizer.py)
- Implement `SecretSanitizer` class providing:
  - `sanitize_text(text: str) -> str`: Regex scrubbing of raw credentials, `snmp_community`, `community`, `password`, `password_hash`, `sshpass`, `api_token`, `secret_key`, `Authorization: Bearer`, `X-Auth-Token`.
  - `sanitize_dict(data: dict) -> dict`: Deep recursive dictionary and list scrubbing without mutating the original dictionary.
  - `sanitize_exception(exc: Exception) -> str`: Converts exception to string and runs structural/textual scrubbing.

#### [MODIFY] [logging.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/utils/logging.py)
- Update `RedactingFormatter` to delegate string scrubbing to `SecretSanitizer.sanitize_text()`.

### 3. Atomic Persistence & Multi-Process Locking Component

#### [MODIFY] [config_service.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/config_service.py)
- Upgrade `save_plans(plans_data)`:
  1. Write to `provision_plans.json.tmp`.
  2. Flush file buffer and execute `os.fsync(f.fileno())`.
  3. Atomic swap via `os.replace(tmp_path, PLANS_PATH)`.
  4. Perform `os.fsync(dir_fd)` on parent directory to ensure directory entry durability.
- Upgrade `load_plans()`:
  1. If `provision_plans.json` load fails due to corruption, log structured error and attempt to recover from `provision_plans.json.bak`.
  2. Never treat `.tmp` files as valid state.

#### [MODIFY] [provision_orchestrator.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/services/provision_orchestrator.py)
- Integrate `SecretService.encrypt_secret` and `decrypt_secret`.
- Implement `fcntl.flock` on `provision_plans.lock` protecting the critical state transition:
  `LOCK` $\rightarrow$ `reload from disk` $\rightarrow$ `validate hash & approval & state` $\rightarrow$ `status = EXECUTING` $\rightarrow$ `persist to disk` $\rightarrow$ `UNLOCK`.
- Wrap all exception strings in `apply_plan` with `SecretSanitizer.sanitize_exception()`.

### 4. Test Suite Component

#### [NEW] [test_sprint_10_9_0_security_hardening.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/test_sprint_10_9_0_security_hardening.py)
- Create comprehensive test suite testing:
  1. **Fernet Encryption & Legacy Migration**: Verify stored secrets start with `FERNET:`, decrypt correctly, and legacy `ENC:` loads into memory but re-saves as `FERNET:`.
  2. **Missing `NETLENS_MASTER_KEY` Error**: Verify missing key raises explicit error and prevents file overwrites.
  3. **Aggressive Secret Leakage Protection**: Inject `SECRET = "NetLens-SNMP-Secret-9f82..."` and search for `SECRET`, `base64(SECRET)`, `repr(SECRET)`, `"community": "SECRET"`, `community=SECRET`, `Authorization: Bearer SECRET` across API responses, `execution_results`, logs, tracebacks, UI payloads, `.tmp`, and `.bak` files.
  4. **Atomic Persistence & Directory `fsync`**: Verify atomic swap sequence, corruption recovery, and `.bak` backup handling.
  5. **Multi-Process Concurrency Test**: Use `multiprocessing.Process` to run concurrent Worker A (PID 1001) and Worker B (PID 1002) attempting simultaneous `apply_plan` calls on `plan-123`, proving Worker A = EXECUTED, Worker B = `CONCURRENT_EXECUTION_BLOCKED`, total executions = 1.
  6. **Quad-Validation Integrity**: Verify `plan_id` + `plan_hash` + `approval` + `approval_hash` + `current_hash` + `risk` + `state` contract remains 100% active.

---

## Verification Plan

### Phase 1: Local Verification
- Run `venv/bin/python3 -m unittest discover -v`.
- Requirement: 177 baseline tests MUST remain PASS + 100% of new 10.9.0 tests PASS (0 FAIL / 0 ERROR).
- Stop after local verification and present audit report.

### Phase 2: Remote Deployment (Requires Explicit Approval)
- Run `scratch/sync_and_restart_netlens.py` to deploy to `192.168.10.51` only when requested by the user.

---
