import json
import os
import requests
from flask import Blueprint, request, jsonify

from app.models.provision_profile import BUILTIN_PROFILES
from app.services.provision_orchestrator import ProvisionOrchestrator
from app.services.provision_reconciliation import ProvisionReconciliationEngine
from app.services.job_engine import JobEngine

provisioning_bp = Blueprint('provisioning', __name__)

def get_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@provisioning_bp.route('/api/v1/provision/profiles', methods=['GET'])
def get_profiles():
    """Return available provision profiles."""
    profiles = []
    for k, v in BUILTIN_PROFILES.items():
        profiles.append({
            "key": k,
            "name": v.name,
            "description": v.description,
            "object_type": v.netbox_object_type,
            "interface_type": "SNMP (161)" if v.zabbix_interface_type == 2 else "Agent (10050)"
        })
    return jsonify({"success": True, "profiles": profiles})

@provisioning_bp.route('/api/v1/provision/clusters', methods=['GET'])
def get_clusters():
    """Return available virtualization clusters from NetBox."""
    config = get_config()
    netbox_cfg = config.get('netbox', {})
    base_url = netbox_cfg.get('url', '').rstrip('/')
    token = netbox_cfg.get('api_token', '')
    
    fallback_clusters = [
        {"id": 18, "name": "10.11.0.233 - SRVPVE52", "type": "PROXMOX-PVE"},
        {"id": 17, "name": "10.11.0.232 - SRVPVE51", "type": "PROXMOX-PVE"},
        {"id": 20, "name": "10.11.0.236 - SRVPVE50", "type": "PROXMOX-PVE"},
        {"id": 16, "name": "10.11.0.228 - SRVPVE28", "type": "PROXMOX-PVE"},
        {"id": 12, "name": "10.11.0.240 - SRVPVE40", "type": "PROXMOX-PVE"},
        {"id": 7, "name": "10.11.0.243 - SRVPVE43", "type": "PROXMOX-PVE"},
        {"id": 19, "name": "10.11.0.244 - SRVPVE44", "type": "PROXMOX-PVE"},
        {"id": 8, "name": "10.11.0.245 - SRVPVE45", "type": "PROXMOX-PVE"},
        {"id": 1, "name": "10.11.0.247 - SRVPVE47", "type": "PROXMOX-PVE"},
        {"id": 9, "name": "10.11.2.212 - SRVPVE12", "type": "PROXMOX-PVE"},
        {"id": 2, "name": "10.11.2.220 - SRVPVETSNEWS1", "type": "PROXMOX-PVE"},
        {"id": 4, "name": "10.11.2.226 - SRVPVE226", "type": "PROXMOX-PVE"},
        {"id": 10, "name": "10.11.3.81 - SRVPVE81", "type": "PROXMOX-PVE"},
        {"id": 5, "name": "10.10.14.110 -SRVPVE10", "type": "PROXMOX-PVE"},
        {"id": 6, "name": "10.10.14.112 - SRVPVE11", "type": "PROXMOX-PVE"},
        {"id": 14, "name": "10.65.0.10 - SRVPVE29", "type": "PROXMOX-PVE"},
        {"id": 11, "name": "10.65.0.12 - SRVPVE42", "type": "PROXMOX-PVE"},
        {"id": 15, "name": "10.65.0.13 - SRVPVE26", "type": "PROXMOX-PVE"},
        {"id": 13, "name": "192.168.50.6 - BANCO DE DADOS VOTURUSSU", "type": "PROXMOX-PVE"}
    ]

    if not base_url:
        return jsonify({"success": True, "clusters": fallback_clusters})
        
    try:
        import requests
        requests.packages.urllib3.disable_warnings()
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        res = requests.get(f"{base_url}/api/virtualization/clusters/", headers=headers, verify=False, timeout=6)
        if res.status_code == 200:
            clusters = []
            for c in res.json().get('results', []):
                clusters.append({
                    "id": c["id"],
                    "name": c.get("name"),
                    "type": c.get("type", {}).get("name", "PROXMOX-PVE") if isinstance(c.get("type"), dict) else "PROXMOX-PVE",
                    "site": c.get("site", {}).get("name") if isinstance(c.get("site"), dict) else None
                })
            resp = jsonify({"success": True, "clusters": clusters})
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp
    except Exception:
        pass

    resp = jsonify({"success": True, "clusters": fallback_clusters})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@provisioning_bp.route('/api/v1/provision/zabbix-templates', methods=['GET'])
def get_zabbix_templates():
    """Return available templates directly from Zabbix server."""
    config = get_config()
    zabbix_cfg = config.get('zabbix', {})
    zb_url = zabbix_cfg.get('url', '').rstrip('/')
    zb_user = zabbix_cfg.get('user', '')
    zb_pass = zabbix_cfg.get('password', '')
    
    fallback_templates = [
        {"id": "10001", "name": "Template OS Linux by Zabbix agent"},
        {"id": "10081", "name": "Template OS Windows by Zabbix agent"},
        {"id": "10643", "name": "01 - WINDOWS"},
        {"id": "10655", "name": "02 - Linux"},
        {"id": "10248", "name": "Template OS Linux SNMP"},
        {"id": "10249", "name": "Windows SNMP"},
        {"id": "10002", "name": "Template Net Cisco IOS SNMP"},
        {"id": "10003", "name": "Template Net Sophos XGS SNMP"},
        {"id": "10004", "name": "Template Net Network Generic SNMP"},
        {"id": "10517", "name": "Proxmox VE by HTTP"}
    ]
    
    if not zb_url or not zb_user:
        resp = jsonify({"success": True, "templates": fallback_templates, "source": "fallback"})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
        
    try:
        import requests
        api_url = f"{zb_url}/api_jsonrpc.php" if not zb_url.endswith('.php') else zb_url
        auth_res = requests.post(api_url, json={
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {"username": zb_user, "password": zb_pass},
            "id": 1
        }, timeout=5).json()
        token = auth_res.get("result")
        
        if token:
            tpl_res = requests.post(api_url, json={
                "jsonrpc": "2.0",
                "method": "template.get",
                "params": {"output": ["templateid", "name"], "limit": 1000, "sortfield": "name"},
                "auth": token,
                "id": 2
            }, timeout=6).json()
            templates = []
            for t in tpl_res.get("result", []):
                templates.append({
                    "id": t.get("templateid"),
                    "name": t.get("name")
                })
            if templates:
                resp = jsonify({"success": True, "templates": templates, "source": "live"})
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return resp
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Provisioning] Falha ao buscar templates Zabbix: {e}")
        
    resp = jsonify({"success": True, "templates": fallback_templates, "source": "fallback"})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@provisioning_bp.route('/api/v1/provision/plan', methods=['POST'])
def plan_provision():
    """Generate deterministic ChangePlan. STRICT READ-ONLY PHASE."""
    data = request.get_json() or {}
    config = get_config()
    try:
        plan = ProvisionOrchestrator.generate_plan(data, config)
        return jsonify({"success": True, "plan": plan})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@provisioning_bp.route('/api/v1/provision/approve', methods=['POST'])
def approve_provision():
    """Approve a ChangePlan for execution."""
    data = request.get_json() or {}
    plan_id = data.get('plan_id')
    plan_hash = data.get('hash')
    if not plan_id:
        return jsonify({"success": False, "error": "plan_id é obrigatório."}), 400
    try:
        approved_plan = ProvisionOrchestrator.approve_plan(plan_id, plan_hash)
        return jsonify({"success": True, "plan": approved_plan})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@provisioning_bp.route('/api/v1/provision/apply', methods=['POST'])
def apply_provision():
    """Apply an approved ChangePlan asynchronously via Job Engine."""
    data = request.get_json() or {}
    plan_id = data.get('plan_id')
    plan_hash = data.get('hash') or data.get('plan_hash')
    if not plan_id:
        return jsonify({"success": False, "error": "plan_id é obrigatório."}), 400
    config = get_config()
    try:
        job = JobEngine.submit_plan_execution(plan_id, config, plan_hash)
        return jsonify({
            "success": True,
            "job_id": job.job_id,
            "plan_id": job.plan_id,
            "plan_hash": job.plan_hash,
            "status": job.status,
            "async": True,
            "message": "Job submetido para execução assíncrona. Use GET /api/v1/provision/jobs/<job_id> para acompanhar."
        }), 202
    except ValueError as ve:
        err_msg = str(ve)
        if "CONCURRENT_EXECUTION_BLOCKED" in err_msg:
            return jsonify({
                "success": False,
                "error": "CONCURRENT_EXECUTION_BLOCKED",
                "message": err_msg
            }), 409
        return jsonify({"success": False, "error": err_msg}), 400
    except KeyError as ke:
        return jsonify({"success": False, "error": str(ke)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@provisioning_bp.route('/api/v1/provision/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Retrieve status of an asynchronous provisioning job."""
    job = JobEngine.get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": f"Job {job_id} não localizado."}), 404
    return jsonify({"success": True, "job": job.to_dict()}), 200

@provisioning_bp.route('/api/v1/provision/jobs/<job_id>/result', methods=['GET'])
def get_job_result(job_id):
    """Retrieve sanitized result of an asynchronous provisioning job."""
    result = JobEngine.get_job_result(job_id)
    if not result:
        return jsonify({"success": False, "error": f"Job {job_id} não localizado."}), 404
    return jsonify({"success": True, "result": result}), 200

@provisioning_bp.route('/api/v1/provision/verify', methods=['POST'])
def verify_provision():
    """Verify state post-apply, calculate drift, and return summary report."""
    data = request.get_json() or {}
    plan_id = data.get('plan_id')
    if not plan_id:
        return jsonify({"success": False, "error": "plan_id é obrigatório."}), 400
    try:
        plan_data = ProvisionOrchestrator.get_plan(plan_id)
        exec_results = plan_data.get('execution_results', {})
        audit_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'audit_log.json')
        report = ProvisionReconciliationEngine.verify_and_reconcile(plan_id, plan_data, exec_results, audit_path)
        return jsonify({"success": True, "report": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@provisioning_bp.route('/api/v1/provision/host', methods=['POST'])
def legacy_provision_host():
    """Legacy backward-compatible endpoint that executes instant Plan -> Approve -> Apply -> Verify."""
    data = request.get_json() or {}
    config = get_config()
    try:
        # Generate Plan
        plan = ProvisionOrchestrator.generate_plan(data, config)
        plan_id = plan["plan_id"]
        # Instant Approve & Apply
        ProvisionOrchestrator.approve_plan(plan_id, plan["hash"])
        exec_res = ProvisionOrchestrator.apply_plan(plan_id, config)
        # Verify
        audit_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'audit_log.json')
        report = ProvisionReconciliationEngine.verify_and_reconcile(plan_id, plan, exec_res["results"], audit_path)
        
        return jsonify({
            "success": True,
            "plan_id": plan_id,
            "hostname": data.get('hostname'),
            "ip": data.get('ip'),
            "results": exec_res["results"],
            "summary_report": report["formatted_report"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
