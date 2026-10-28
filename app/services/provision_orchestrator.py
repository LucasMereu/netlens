import uuid
import json
import hashlib
import requests
import time
import base64
import threading
from typing import Dict, Any, List, Optional
from app.models.provision_profile import BUILTIN_PROFILES
from app.models.provision_dependency import CanonicalHostIdentity, DependencyStatus
from app.services.provision_capability_engine import ProvisionCapabilityEngine
from app.services.provision_profile_engine import ProvisionProfileEngine
from app.policies.provision_policy_engine import ProvisionPolicyEngine
from app.services.provision_dependency_engine import ProvisionDependencyEngine
from app.services.provision_idempotency_engine import ProvisionIdempotencyEngine
from app.services.provision_risk_engine import ProvisionRiskEngine
from app.services.config_service import ConfigService

import fcntl
import os
from app.services.secret_service import SecretService
from app.utils.sanitizer import SecretSanitizer
from app.services.provision_drivers.netbox_provisioner import NetBoxProvisioner
from app.services.provision_drivers.zabbix_provisioner import ZabbixProvisioner
from app.services.provision_drivers.librenms_provisioner import LibreNMSProvisioner
from app.services.provision_drivers.netdisco_provisioner import NetDiscoProvisioner

# Thread-safe and process-safe locks for plan store operations
_PLAN_LOCK = threading.Lock()
_PLAN_STORE: Dict[str, Dict[str, Any]] = {}
LOCK_FILE_PATH = os.path.join(ConfigService.CONFIG_DIR, 'provision_plans.lock')

class ProcessFileLock:
    def __init__(self, lockfile=LOCK_FILE_PATH):
        self.lockfile = lockfile
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.lockfile, os.O_CREAT | os.O_RDWR)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None

def _load_plan_store_into_memory():
    global _PLAN_STORE
    try:
        with ProcessFileLock():
            disk_plans = ConfigService.load_plans(force_reload=True)
            for p_id, p_data in disk_plans.items():
                item = p_data.copy()
                if "_secret_snmp_community" in item and isinstance(item["_secret_snmp_community"], str):
                    item["_secret_snmp_community"] = SecretService.decrypt_secret(item["_secret_snmp_community"])
                _PLAN_STORE[p_id] = item
    except Exception:
        pass

def _persist_plan_store():
    try:
        with ProcessFileLock():
            serializable = {}
            for p_id, p_data in _PLAN_STORE.items():
                item = p_data.copy()
                if "_secret_snmp_community" in item and isinstance(item["_secret_snmp_community"], str):
                    item["_secret_snmp_community"] = SecretService.encrypt_secret(item["_secret_snmp_community"])
                serializable[p_id] = item
            ConfigService.save_plans(serializable)
    except Exception:
        pass

# Initialize memory store from disk on module import
_load_plan_store_into_memory()

class ProvisionOrchestrator:

    _load_plans = staticmethod(_load_plan_store_into_memory)
    _persist_plan_store = staticmethod(_persist_plan_store)

    @staticmethod
    def generate_plan(input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate deterministic ChangePlan with Policy, Dependency, Idempotency, and Risk Engines.
        STRICT REQUIREMENT: NO WRITE API CALLS DURING PLAN PHASE.
        Secrets (snmp_community) are redacted from output.
        """
        hostname = input_data.get('hostname', '').strip()
        ip = input_data.get('ip', '').strip()
        site = input_data.get('site', 'RedeTV HQ').strip()
        model = input_data.get('model', 'Generic Device').strip()
        profile_name = input_data.get('profile', 'NETWORK_SWITCH').upper()
        snmp_version = input_data.get('snmp_version', 'v2c').strip()
        raw_snmp_community = input_data.get('snmp_community', 'public').strip()

        if not hostname or not ip:
            raise ValueError("Hostname e IP são obrigatórios para geração do plano.")

        # 1. EVALUATE POLICIES (Sprint 10.7.5)
        policy_result = ProvisionPolicyEngine.evaluate_policies(input_data, profile_name)
        if not policy_result.passed:
            violation_msgs = [v.message for v in policy_result.violations]
            raise ValueError(f"POLICY_VIOLATION: O plano foi rejeitado por violação de políticas corporativas: {'; '.join(violation_msgs)}")

        # 2. CANONICAL HOST IDENTITY & DEPENDENCY DISCOVERY (Sprint 10.7.6 - Read-Only)
        canonical = CanonicalHostIdentity(hostname=hostname, ip=ip, profile=profile_name, site=site)
        discovery_results = ProvisionDependencyEngine.discover_all(canonical, config)

        # 3. IDEMPOTENCY ANALYSIS & CONFLICT DETECTION
        can_proceed, system_actions, block_reasons = ProvisionIdempotencyEngine.classify_and_generate_actions(canonical, discovery_results)
        if not can_proceed:
            raise ValueError(f"PLAN_BLOCKED: Conflito ou inconsistência detectada nos sistemas: {'; '.join(block_reasons)}")

        # 4. RISK ASSESSMENT (Sprint 10.7.8)
        risk_assessment = ProvisionRiskEngine.assess_risk(input_data, profile_name, policy_result, discovery_results)

        profile = ProvisionProfileEngine.get_profile(profile_name)
        capabilities = ProvisionCapabilityEngine.get_capabilities(model=model, profile=profile_name)

        # Extract optional NetBox VM / Custom fields
        cluster_val = input_data.get('cluster') or input_data.get('cluster_id')
        vcpus_val = input_data.get('vcpus')
        memory_val = input_data.get('memory')
        disk_val = input_data.get('disk')
        cf = dict(input_data.get('custom_fields', {}) or {})
        if input_data.get('hd'):
            cf['HD'] = str(input_data['hd']).strip()
        if input_data.get('ram_text'):
            cf['Memoria'] = str(input_data['ram_text']).strip()
        elif memory_val:
            cf.setdefault('Memoria', f"{memory_val} MB")
        if input_data.get('processor'):
            cf['Processador'] = str(input_data['processor']).strip()
        elif vcpus_val:
            cf.setdefault('Processador', f"{vcpus_val} vCPUs")
        if input_data.get('url'):
            cf['URL'] = str(input_data['url']).strip()

        # Dynamic Resolution (Read-only GET requests)
        zabbix_template_val = (input_data.get('zabbix_template') or input_data.get('template') or '').strip() or None
        netbox_resolved = ProvisionProfileEngine.resolve_netbox_objects(
            config=config,
            profile=profile,
            site_name=site,
            model_name=model,
            ip_address=ip,
            hostname=hostname,
            cluster=cluster_val,
            vm_resources={"vcpus": vcpus_val, "memory": memory_val, "disk": disk_val},
            custom_fields=cf
        )
        zabbix_resolved = ProvisionProfileEngine.resolve_zabbix_objects(
            config=config,
            profile=profile,
            hostname=hostname,
            ip_address=ip,
            custom_template=zabbix_template_val
        )

        # Plan ID generation
        plan_seq = str(uuid.uuid4().hex[:8]).upper()
        plan_id = f"PROV-2026-{plan_seq}"

        # Operations DAG with Idempotent Actions (CREATE vs REUSE)
        netbox_details = {
            "role": profile.netbox_role_slug,
            "site": netbox_resolved['site_name'],
            "model": model,
            "status": "Active"
        }
        if profile.netbox_object_type == "virtualmachine":
            netbox_details["cluster"] = netbox_resolved.get("cluster_name")
            if netbox_resolved.get("vcpus"): netbox_details["vcpus"] = netbox_resolved["vcpus"]
            if netbox_resolved.get("memory"): netbox_details["memory"] = netbox_resolved["memory"]
            if netbox_resolved.get("disk"): netbox_details["disk"] = netbox_resolved["disk"]
        if netbox_resolved.get("custom_fields"):
            netbox_details["custom_fields"] = netbox_resolved["custom_fields"]

        operations = [
            {
                "system": "NetBox",
                "operation": f"CREATE_{profile.netbox_object_type.upper()}",
                "object": hostname,
                "action": system_actions.get("netbox", "CREATE"),
                "details": netbox_details,
                "idempotency_key": f"netbox-{hostname}"
            },
            {
                "system": "NetBox",
                "operation": "ALLOCATE_IP",
                "object": netbox_resolved['ip_address_with_mask'],
                "action": system_actions.get("netbox", "CREATE"),
                "details": {
                    "address": netbox_resolved['ip_address_with_mask'],
                    "status": "Active"
                },
                "idempotency_key": f"netbox-ip-{ip}"
            },
            {
                "system": "Zabbix",
                "operation": "CREATE_HOST",
                "object": hostname,
                "action": system_actions.get("zabbix", "CREATE"),
                "details": {
                    "groups": zabbix_resolved['group_names'],
                    "templates": zabbix_resolved['template_names'],
                    "interface": f"{ip}:{zabbix_resolved['port']}",
                    "interface_type": "SNMP" if zabbix_resolved['interface_type'] == 2 else "Agent"
                },
                "idempotency_key": f"zabbix-{hostname}"
            },
            {
                "system": "LibreNMS",
                "operation": "ENROLL_DEVICE",
                "object": ip,
                "action": system_actions.get("librenms", "CREATE"),
                "details": {
                    "protocol": profile.librenms_protocol,
                    "version": profile.librenms_version,
                    "port": profile.librenms_port
                },
                "idempotency_key": f"librenms-{ip}"
            },
            {
                "system": "NetDisco",
                "operation": "TOPOLOGY_DISCOVERY",
                "object": ip,
                "action": "DISCOVERY" if system_actions.get("netdisco") == "CREATE" else "REUSE",
                "details": {
                    "scan": "L2/L3 Topology & CDP/LLDP Neighbors",
                    "protocols": profile.netdisco_protocols
                },
                "idempotency_key": f"netdisco-{ip}"
            }
        ]

        # Deterministic Plan Representation for Hash Calculation (including risk score)
        hash_payload = {
            "hostname": hostname,
            "ip": ip,
            "site": site,
            "model": model,
            "profile": profile_name,
            "operations": operations,
            "risk_score": risk_assessment.risk_score
        }
        hash_str = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
        plan_hash = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()

        plan_data = {
            "plan_id": plan_id,
            "profile": profile_name,
            "risk": risk_assessment.risk_level.value,
            "risk_assessment": risk_assessment.to_dict(),
            "status": "PENDING_APPROVAL",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "input": {
                "hostname": hostname,
                "ip": ip,
                "site": site,
                "model": model,
                "snmp_version": snmp_version,
                "snmp_community": "[REDACTED]",  # Secret Redaction
                "zabbix_template": zabbix_resolved['template_names'][0] if zabbix_resolved.get('template_names') else ""
            },
            "canonical_identity": canonical.to_dict(),
            "policy_result": policy_result.to_dict(),
            "discovery_results": {sys: res.to_dict() for sys, res in discovery_results.items()},
            "system_actions": system_actions,
            "capabilities": capabilities,
            "resolved_objects": {
                "netbox": netbox_resolved,
                "zabbix": zabbix_resolved
            },
            "operations": operations,
            "dag_graph": ProvisionDependencyEngine.build_dependency_dag(canonical),
            "hash": plan_hash,
            # Private internal secrets stored in memory ONLY (not exported to JSON output)
            "_secret_snmp_community": raw_snmp_community
        }

        with _PLAN_LOCK:
            _PLAN_STORE[plan_id] = plan_data
            _persist_plan_store()

        # Return sanitized public representation
        public_plan = plan_data.copy()
        if "_secret_snmp_community" in public_plan:
            del public_plan["_secret_snmp_community"]

        return public_plan

    @staticmethod
    def get_plan(plan_id: str) -> Dict[str, Any]:
        with _PLAN_LOCK:
            _load_plan_store_into_memory()
            if plan_id not in _PLAN_STORE:
                raise KeyError(f"Plan {plan_id} não localizado.")
            res = _PLAN_STORE[plan_id].copy()
            if "_secret_snmp_community" in res:
                del res["_secret_snmp_community"]
            return res

    @staticmethod
    def approve_plan(plan_id: str, plan_hash: Optional[str] = None) -> Dict[str, Any]:
        with _PLAN_LOCK:
            _load_plan_store_into_memory()
            if plan_id not in _PLAN_STORE:
                raise KeyError(f"Plan {plan_id} não localizado.")
            
            plan = _PLAN_STORE[plan_id]

            # Re-verify internal hash integrity against current operations
            hash_payload = {
                "hostname": plan.get("canonical_identity", {}).get("hostname", plan["input"]["hostname"]),
                "ip": plan.get("canonical_identity", {}).get("ip", plan["input"]["ip"]),
                "site": plan.get("canonical_identity", {}).get("site", plan["input"]["site"]),
                "model": plan["input"]["model"],
                "profile": plan["profile"],
                "operations": plan["operations"],
                "risk_score": plan.get("risk_assessment", {}).get("risk_score", 0)
            }
            calc_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()
            
            if calc_hash != plan["hash"]:
                raise ValueError("TAMPER_DETECTED: O conteúdo das operações foi modificado após a geração do plano. Aprovação rejeitada.")

            if plan_hash and plan["hash"] != plan_hash:
                raise ValueError("TAMPER_DETECTED: O hash do plano não corresponde ao hash gerado. Aprovação rejeitada.")

            plan["status"] = "APPROVED"
            plan["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            plan["approved_plan_hash"] = plan["hash"]
            _persist_plan_store()

            res = plan.copy()
            if "_secret_snmp_community" in res:
                del res["_secret_snmp_community"]
            return res

    @staticmethod
    def apply_plan(plan_id: str, config: Dict[str, Any], plan_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes approved plan against NetBox, Zabbix, LibreNMS, and NetDisco.
        Quad-Validation: Requires status == APPROVED, plan hash match, approval hash match, risk != CRITICAL.
        """
        with _PLAN_LOCK:
            _load_plan_store_into_memory()
            if plan_id not in _PLAN_STORE:
                raise KeyError(f"Plan {plan_id} não localizado.")

            plan = _PLAN_STORE[plan_id]

            if plan["status"] in ("EXECUTING", "APPLIED", "COMMITTED"):
                raise ValueError(f"CONCURRENT_EXECUTION_BLOCKED: O plano {plan_id} já está em execução ou foi aplicado (status: {plan['status']}).")

            if plan["status"] != "APPROVED":
                raise ValueError(f"UNAPPROVED_PLAN: O plano {plan_id} precisa ser APROVADO antes da execução (status atual: {plan['status']}).")

            # Tamper Check: verify current hash vs stored hash & approved hash
            hash_payload = {
                "hostname": plan.get("canonical_identity", {}).get("hostname", plan["input"]["hostname"]),
                "ip": plan.get("canonical_identity", {}).get("ip", plan["input"]["ip"]),
                "site": plan.get("canonical_identity", {}).get("site", plan["input"]["site"]),
                "model": plan["input"]["model"],
                "profile": plan["profile"],
                "operations": plan["operations"],
                "risk_score": plan.get("risk_assessment", {}).get("risk_score", 0)
            }
            calc_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()

            if calc_hash != plan["hash"] or plan.get("approved_plan_hash") != plan["hash"]:
                raise ValueError("TAMPER_DETECTED: O hash do plano aprovado foi adulterado antes da execução. Aplicação abortada.")

            if plan_hash and plan["hash"] != plan_hash:
                raise ValueError("TAMPER_DETECTED: O hash informado no Apply não corresponde ao hash do plano aprovado. Aplicação abortada.")

            risk_info = plan.get("risk_assessment", {})
            if not risk_info.get("can_apply", True) or plan.get("risk") == "CRITICAL":
                raise ValueError(f"CRITICAL_RISK_BLOCKED: O plano {plan_id} possui Risco CRÍTICO e foi bloqueado pelo Risk Engine.")

            plan["status"] = "EXECUTING"
            _persist_plan_store()

        results = {}
        snmp_comm = plan.get("_secret_snmp_community", "public")
        inp = plan["input"]
        netbox_resolved = plan["resolved_objects"]["netbox"]
        zabbix_resolved = plan["resolved_objects"]["zabbix"]
        system_actions = plan.get("system_actions", {})

        # Dispatch execution to dedicated provision drivers
        # Uses requests (requests.get, requests.post, requests.patch) delegated to provision_drivers
        results["netbox"] = NetBoxProvisioner.provision(
            inp=inp,
            config=config,
            resolved=netbox_resolved,
            action=system_actions.get("netbox")
        )

        results["zabbix"] = ZabbixProvisioner.provision(
            inp=inp,
            config=config,
            resolved=zabbix_resolved,
            action=system_actions.get("zabbix"),
            snmp_community=snmp_comm
        )

        results["librenms"] = LibreNMSProvisioner.provision(
            inp=inp,
            config=config,
            snmp_community=snmp_comm,
            action=system_actions.get("librenms")
        )

        results["netdisco"] = NetDiscoProvisioner.provision(
            inp=inp,
            config=config
        )

        with _PLAN_LOCK:
            plan["status"] = "APPLIED"
            plan["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            plan["execution_results"] = results
            _persist_plan_store()

        return {
            "plan_id": plan_id,
            "status": "APPLIED",
            "results": results
        }
