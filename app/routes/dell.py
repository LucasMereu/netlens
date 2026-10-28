import os
from flask import Blueprint, jsonify, request
from app.drivers.dell.driver import DellDriver
from app.models.device import DeviceIdentity
from app.models.constants import Vendor, Platform
from app.services.config_service import ConfigService

dell_bp = Blueprint('dell', __name__)

@dell_bp.route('/api/backup-config', methods=['POST'])
def backup_config():
    data = request.json or {}
    ip = data.get("ip")
    username = data.get("username")
    password = data.get("password")
    
    if not ip or not username or not password:
        return jsonify({"success": False, "error": "IP, usuario e senha sao obrigatorios."}), 400
        
    try:
        identity = DeviceIdentity(
            device_id=ip,
            hostname=ip,
            management_ip=ip,
            vendor=Vendor.DELL,
            platform=Platform.DELL_OS9
        )
        driver = DellDriver(identity, username=username, password=password)
        driver.connect()
        config_text = driver.get_running_config()
        driver.disconnect()
        return jsonify({"success": True, "content": config_text, "ip": ip})
    except Exception as e:
        return jsonify({"success": False, "error": f"Erro de conexao/execucao SSH via CLI: {str(e)}"}), 500

@dell_bp.route('/api/dell-alignment/plan')
def get_dell_alignment_plan():
    plan_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'reports', 'implementation_plan.md')
    try:
        if os.path.exists(plan_path):
            with open(plan_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"success": True, "content": content})
        else:
            return jsonify({"success": False, "error": "Plano de implementacao nao encontrado."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dell_bp.route('/api/dell-alignment/validate', methods=['POST'])
def dell_alignment_validate():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"success": False, "error": "Usuario e senha SSH sao obrigatorios."}), 400
        
    config = ConfigService.load_config()
    dells = config.get("dell_switches", [])
    if not dells:
        return jsonify({"success": False, "error": "Nenhum switch Dell configurado em config.json"}), 400
        
    results = {}
    
    for device in dells:
        ip = device["ip"]
        name = device["name"]
        try:
            identity = DeviceIdentity(
                device_id=ip,
                hostname=name,
                management_ip=ip,
                vendor=Vendor.DELL,
                platform=Platform.DELL_OS9
            )
            driver = DellDriver(identity, username=username, password=password)
            driver.connect()
            align_data = driver.validate_configuration()
            driver.disconnect()
            
            results[ip] = {
                "name": name,
                "role": device.get("role", "core"),
                "default_vlan": align_data["default_vlan"],
                "pvid": align_data["pvid"],
                "status": "ok",
                "details": f"VLAN Default: {align_data['default_vlan']} | PVID PC49: {align_data['pvid']}"
            }
        except Exception as e:
            results[ip] = {
                "name": name,
                "role": device.get("role", "core"),
                "default_vlan": "Erro",
                "pvid": "Erro",
                "status": "error",
                "details": f"Erro de conexao/execucao: {str(e)}"
            }
            
    aligned = True
    error_reasons = []
    
    all_ips = [d["ip"] for d in dells]
    for ip in all_ips:
        if results.get(ip, {}).get("status") != "ok":
            aligned = False
            error_reasons.append(f"Falha de comunicacao com o switch {results.get(ip, {}).get('name')}.")
            
    if aligned and dells:
        core_switches = [d for d in dells if d.get("role") == "core"]
        core_vlans = {d["ip"]: results[d["ip"]]["default_vlan"] for d in core_switches if d["ip"] in results}
        if len(set(core_vlans.values())) > 1:
            aligned = False
            for d in core_switches:
                if d["ip"] in results:
                    results[d["ip"]]["status"] = "warning"
            core_summary = " vs ".join([f"{d['name']} ({core_vlans[d['ip']]})" for d in core_switches if d["ip"] in core_vlans])
            error_reasons.append(f"Divergencia de VLAN Default entre Cores: {core_summary}.")
            
        all_pvids = {d["ip"]: results[d["ip"]]["pvid"] for d in dells if d["ip"] in results}
        if len(set(all_pvids.values())) > 1:
            aligned = False
            for ip in all_ips:
                if ip in results:
                    results[ip]["status"] = "warning"
            pvid_summary = " vs ".join([f"{d['name']} ({all_pvids[d['ip']]})" for d in dells if d["ip"] in all_pvids])
            error_reasons.append(f"Divergencia de PVID no Port-channel 49: {pvid_summary}.")
            
    summary_msg = "Alinhamento Conforme! Todos os switches estao com as configuracoes sincronizadas." if aligned else " | ".join(error_reasons)
    
    return jsonify({
        "success": True,
        "aligned": aligned,
        "switches": results,
        "summary": summary_msg
    })
