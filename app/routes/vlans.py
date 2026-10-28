import os
from flask import Blueprint, jsonify, request
from app.services.vlan_service import VlanService
from app.services.config_service import ConfigService
from app.clients import is_mock_mode, get_netdisco_client

vlans_bp = Blueprint('vlans', __name__)

MOCK_VLANS = [
    {
        "mismatch_type": "native_vlan_mismatch",
        "severity": "critical",
        "device_a": "10.100.1.2",
        "device_a_name": "DIST-SW01",
        "port_a": "GigabitEthernet1/0/1",
        "port_a_pvid": 1,
        "device_b": "10.100.10.10",
        "device_b_name": "ACC-SW-T1-1",
        "port_b": "GigabitEthernet0/1",
        "port_b_pvid": 99,
        "description": "Divergencia de VLAN nativa (PVID): Lado A (GigabitEthernet1/0/1) usa VLAN nativa 1, enquanto o Lado B (GigabitEthernet0/1) usa VLAN nativa 99. Isso causa vazamento de pacotes untagged."
    },
    {
        "mismatch_type": "allowed_vlans_mismatch",
        "severity": "warning",
        "device_a": "10.100.1.1",
        "device_a_name": "CORE-SW01",
        "port_a": "TenGigabitEthernet1/1/2",
        "port_a_allowed": [1, 10, 20, 30, 40],
        "device_b": "10.100.1.3",
        "device_b_name": "DIST-SW02",
        "port_b": "TenGigabitEthernet1/1/1",
        "port_b_allowed": [1, 10, 20],
        "description": "Divergencia nas VLANs permitidas (Trunk): VLANs permitidas apenas no Lado A: [30, 40]. O trafego para estas VLANs sera dropado no Switch de Distribuicao."
    }
]

@vlans_bp.route('/api/vlans')
def get_vlans():
    force_refresh = request.args.get('refresh', default='false').lower() == 'true'
    try:
        data = VlanService.audit_vlans(force_refresh=force_refresh)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "fallback_data": MOCK_VLANS}), 500

@vlans_bp.route('/api/vlans/validate-link', methods=['POST'])
def validate_vlan_link():
    data = request.json or {}
    device_a = data.get("device_a")
    device_b = data.get("device_b")
    
    if not device_a or not device_b:
        return jsonify({"success": False, "error": "device_a e device_b sao obrigatorios."}), 400
        
    try:
        res = VlanService.validate_link(device_a, device_b)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@vlans_bp.route('/api/vlan1-report')
def get_vlan1_report():
    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'reports', 'switch_vlan1_audit_report.md')
    try:
        if os.path.exists(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"success": True, "content": content})
        else:
            return jsonify({"success": False, "error": "Relatorio de auditoria de VLAN 1 nao encontrado."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@vlans_bp.route('/api/vlan-trunk-report')
def get_vlan_trunk_report():
    if is_mock_mode():
        return jsonify({"success": True, "content": "# Relatorio de Trunks (Demonstracao)\nModo de demonstracao ativo."})
        
    try:
        mismatches = VlanService.audit_vlans()
        content = build_vlan_trunk_report_markdown(mismatches)
        return jsonify({"success": True, "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_device_vendor_map():
    vendor_map = {}
    nd = get_netdisco_client()
    if nd:
        try:
            devices = nd.get_devices()
            for d in devices:
                ip = d.get("ip")
                if ip:
                    vendor_map[ip] = classify_device_vendor(d)
        except Exception as e:
            print(f"[VLAN REPORT] Erro ao obter mapa de vendors: {e}")
    return vendor_map

def classify_device_vendor(dev):
    model = str(dev.get("model", "")).lower()
    name = str(dev.get("name", "")).lower()
    vendor = str(dev.get("vendor", "") or dev.get("vendor_name", "") or "").lower()
    
    if "s4048" in model or "dell" in name or "dell" in vendor:
        return "dell"
    elif any(x in model for x in ["2910", "2930", "2920", "j9983", "aruba", "procurve", "hp_dc"]):
        return "aruba"
    elif any(x in model for x in ["v1910", "1920", "2928", "2952", "5120", "baseline", "3com", "comware", "h3c", "a5120"]):
        return "comware"
    
    if "sw" in name or "switch" in name:
        if "dell" in name:
            return "dell"
        elif "hp" in name or "aruba" in name:
            return "aruba"
        else:
            return "comware"
            
    return "unknown"

def generate_vlan_commands(vlan_id, vendor, port, cmd_type="untagged"):
    if vendor == "dell":
        if cmd_type == "untagged":
            return [
                "configure terminal",
                f"interface Vlan {vlan_id}",
                f"  untagged {port}",
                "exit",
                "end",
                "write memory"
            ]
        else:
            return [
                "configure terminal",
                f"interface Vlan {vlan_id}",
                f"  tagged {port}",
                "exit",
                "end",
                "write memory"
            ]
    elif vendor == "aruba":
        if cmd_type == "untagged":
            return [
                "configure terminal",
                f"vlan {vlan_id}",
                f"  untagged {port}",
                "exit",
                "end",
                "write memory"
            ]
        else:
            return [
                "configure terminal",
                f"vlan {vlan_id}",
                f"  tagged {port}",
                "exit",
                "end",
                "write memory"
            ]
    elif vendor == "comware":
        if cmd_type == "untagged":
            return [
                "system-view",
                f"vlan {vlan_id}",
                "quit",
                f"interface {port}",
                f"  port trunk pvid vlan {vlan_id}",
                f"  port trunk permit vlan {vlan_id}",
                "quit",
                "save"
            ]
        else:
            return [
                "system-view",
                f"vlan {vlan_id}",
                "quit",
                f"interface {port}",
                f"  port trunk permit vlan {vlan_id}",
                "quit",
                "save"
            ]
    return []

def build_vlan_trunk_report_markdown(mismatches):
    vendor_map = get_device_vendor_map()
    
    dells = ["172.16.11.248", "172.16.11.249", "172.16.11.250", "192.168.4.13", "10.11.0.251"]
    dell_mismatches = []
    for m in mismatches:
        if m.get("device_a") in dells or m.get("device_b") in dells:
            dell_mismatches.append(m)
            
    seen_links = set()
    unique_mismatches = []
    for m in dell_mismatches:
        ip_a = "172.16.11.249" if m.get("device_a") == "192.168.4.13" else m.get("device_a")
        ip_b = "172.16.11.249" if m.get("device_b") == "192.168.4.13" else m.get("device_b")
        
        link_key = tuple(sorted([f"{ip_a}:{m.get('port_a')}", f"{ip_b}:{m.get('port_b')}", m.get("mismatch_type")]))
        if link_key not in seen_links:
            seen_links.add(link_key)
            unique_mismatches.append(m)
            
    native_mismatches = [m for m in unique_mismatches if m.get("mismatch_type") == "native_vlan_mismatch"]
    allowed_mismatches = [m for m in unique_mismatches if m.get("mismatch_type") == "allowed_vlans_mismatch"]
    
    md = []
    md.append("# Relatorio Geral de Inconsistencias de VLANs nos Trunks (Cores & Bordas)\n")
    md.append("Este relatorio apresenta a analise viva de todas as portas de interconexao (uplinks/trunks) entre os switches core Dell e os switches de acesso/borda, identificando divergencias criticas de VLAN Nativa (PVID) e de VLANs permitidas (taggeadas).\n")
    
    md.append("## Resumo Executivo")
    md.append(f"- **Total de Divergencias Encontradas:** {len(unique_mismatches)}")
    md.append(f"  - **Erros de VLAN Nativa (PVID Mismatch - Critico):** {len(native_mismatches)}")
    md.append(f"  - **Erros de VLANs Permitidas no Trunk (Allowed Mismatch - Atencao):** {len(allowed_mismatches)}\n")
    
    md.append("---")
    md.append("## 1. Divergencias Criticas de VLAN Nativa (PVID)")
    md.append("Esses erros podem causar vazamento de pacotes untagged entre VLANs distintas, alem de poder provocar loops ou portas derrubadas no Spanning Tree devido a *PVID Mismatch*.\n")
    
    for idx, m in enumerate(native_mismatches, 1):
        dev_a_ip = m.get("device_a")
        dev_a_clean = "172.16.11.249" if dev_a_ip == "192.168.4.13" else dev_a_ip
        dev_a_name = m.get("device_a_name")
        port_a = m.get("port_a")
        pvid_a = m.get("port_a_pvid")
        vendor_a = vendor_map.get(dev_a_ip, "dell")
        
        dev_b_ip = m.get("device_b")
        dev_b_name = m.get("device_b_name")
        port_b = m.get("port_b")
        pvid_b = m.get("port_b_pvid")
        vendor_b = vendor_map.get(dev_b_ip, "unknown")
        
        md.append(f"### Link {idx}: {dev_a_name} ({dev_a_clean}) ⇄ {dev_b_name} ({dev_b_ip})")
        md.append(f"- **Porta Lado A:** `{port_a}` | PVID atual: `{pvid_a}`")
        md.append(f"- **Porta Lado B:** `{port_b}` | PVID atual: `{pvid_b}`")
        md.append(f"- **Descricao:** {m.get('description')}\n")
        
        md.append("**Comandos CLI de Correcao Sugeridos:**")
        target_pvid = pvid_b if pvid_a == 1 else pvid_a
        
        md.append(f"**No {dev_a_name} ({dev_a_clean}) [{vendor_a.upper()}]:**")
        md.append("```text")
        for cmd in generate_vlan_commands(target_pvid, vendor_a, port_a, "untagged"):
            md.append(cmd)
        md.append("```")
        
        md.append(f"**No {dev_b_name} ({dev_b_ip}) [{vendor_b.upper()}]:**")
        md.append("```text")
        for cmd in generate_vlan_commands(target_pvid, vendor_b, port_b, "untagged"):
            md.append(cmd)
        md.append("```\n")
        md.append("---")
        
    md.append("\n## 2. Divergencias de VLANs Permitidas (Trunk Allowed)")
    md.append("Esses erros impedem que o trafego de certas VLANs passe pelo trunk, pois elas estao permitidas em um switch mas bloqueadas/nao configuradas no switch vizinho.\n")
    
    for idx, m in enumerate(allowed_mismatches, 1):
        dev_a_ip = m.get("device_a")
        dev_a_clean = "172.16.11.249" if dev_a_ip == "192.168.4.13" else dev_a_ip
        dev_a_name = m.get("device_a_name")
        port_a = m.get("port_a")
        allowed_a = m.get("port_a_allowed")
        vendor_a = vendor_map.get(dev_a_ip, "dell")
        
        dev_b_ip = m.get("device_b")
        dev_b_name = m.get("device_b_name")
        port_b = m.get("port_b")
        allowed_b = m.get("port_b_allowed")
        vendor_b = vendor_map.get(dev_b_ip, "unknown")
        
        md.append(f"### Link {idx}: {dev_a_name} ({dev_a_clean}) ⇄ {dev_b_name} ({dev_b_ip})")
        md.append(f"- **Porta Lado A:** `{port_a}` | VLANs permitidas: `{allowed_a}`")
        md.append(f"- **Porta Lado B:** `{port_b}` | VLANs permitidas: `{allowed_b}`")
        md.append(f"- **Descricao:** {m.get('description')}\n")
        
        set_a = set(allowed_a) if allowed_a else set()
        set_b = set(allowed_b) if allowed_b else set()
        
        missing_in_a = set_b.difference(set_a)
        missing_in_b = set_a.difference(set_b)
        
        md.append("**Comandos CLI de Correcao Sugeridos:**")
        if missing_in_a:
            md.append(f"**No {dev_a_name} ({dev_a_clean}) [{vendor_a.upper()}] - Adicionar VLANs {sorted(list(missing_in_a))}:**")
            md.append("```text")
            for vlan in sorted(list(missing_in_a)):
                for cmd in generate_vlan_commands(vlan, vendor_a, port_a, "tagged"):
                    md.append(cmd)
            md.append("```")
            
        if missing_in_b:
            md.append(f"**No {dev_b_name} ({dev_b_ip}) [{vendor_b.upper()}] - Adicionar VLANs {sorted(list(missing_in_b))}:**")
            md.append("```text")
            for vlan in sorted(list(missing_in_b)):
                for cmd in generate_vlan_commands(vlan, vendor_b, port_b, "tagged"):
                    md.append(cmd)
            md.append("```\n")
        md.append("---")
        
    return "\n".join(md)
