# NetLens Inventory Routes (Unified: Servers, Switches, Firewalls, WiFi Controllers, WiFi APs)
from flask import Blueprint, jsonify, request, session
from app.services.server_inventory_service import ServerInventoryService

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/api/inventory/servers', methods=['GET'])
def get_server_inventory():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    force_refresh = request.args.get('force', 'false').lower() == 'true'
    result = ServerInventoryService.get_server_inventory(force_refresh=force_refresh)
    return jsonify(result)

@inventory_bp.route('/api/inventory/devices/<category>', methods=['GET'])
def get_category_inventory(category):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    force_refresh = request.args.get('force', 'false').lower() == 'true'
    result = ServerInventoryService.get_category_inventory(category, force_refresh=force_refresh)
    return jsonify(result)

@inventory_bp.route('/api/firewall/overview', methods=['GET'])
def get_firewall_overview():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    from app.services.sophos_service import SophosService
    force = request.args.get('force', 'false').lower() == 'true'
    host = request.args.get('host', '10.1.1.2')
    data = SophosService.get_firewall_overview(force=force, host=host)
    return jsonify(data)

@inventory_bp.route('/api/firewall/appliances', methods=['GET', 'POST'])
def manage_firewall_appliances():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    from app.services.config_service import ConfigService
    cfg = ConfigService.load_config()
    firewalls = cfg.get("firewalls", [])

    if request.method == 'GET':
        from app.services.sophos_service import SophosService
        return jsonify({'success': True, 'appliances': SophosService.get_appliances()})
    
    # POST: Criar novo firewall
    data = request.json or {}
    host = (data.get('host') or '').strip()
    name = (data.get('name') or '').strip()
    if not host or not name:
        return jsonify({'success': False, 'error': 'Nome e Endereço IP do Firewall são obrigatórios'}), 400

    import uuid
    fw_id = data.get('id') or f"fw-{uuid.uuid4().hex[:8]}"
    new_fw = {
        "id": fw_id,
        "name": name,
        "host": host,
        "port": str(data.get('port') or "4444").strip(),
        "city": (data.get('city') or 'Praça Remota').strip(),
        "role": (data.get('role') or 'Borda & Gateway').strip(),
        "location": (data.get('location') or data.get('city') or 'Praça Remota').strip(),
        "user": (data.get('user') or 'netlens_api').strip(),
        "password": data.get('password') or '@NetLensSecurePass2026!',
        "use_default_auth": bool(data.get('use_default_auth', True)),
        "enabled": bool(data.get('enabled', True))
    }

    # Evitar duplicidade de host
    existing = next((f for f in firewalls if f.get('host') == host), None)
    if existing:
        return jsonify({'success': False, 'error': f'Já existe um firewall cadastrado com o IP {host}'}), 400

    firewalls.append(new_fw)
    cfg['firewalls'] = firewalls
    ConfigService.save_config(cfg)
    return jsonify({'success': True, 'appliance': new_fw, 'message': 'Firewall cadastrado com sucesso!'})

@inventory_bp.route('/api/firewall/appliances/<fw_id>', methods=['PUT', 'DELETE'])
def modify_firewall_appliance(fw_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.config_service import ConfigService
    cfg = ConfigService.load_config()
    firewalls = cfg.get("firewalls", [])

    idx = next((i for i, f in enumerate(firewalls) if f.get('id') == fw_id or f.get('host') == fw_id), None)
    if idx is None:
        return jsonify({'success': False, 'error': 'Firewall não encontrado'}), 404

    if request.method == 'DELETE':
        removed = firewalls.pop(idx)
        cfg['firewalls'] = firewalls
        ConfigService.save_config(cfg)
        return jsonify({'success': True, 'message': f"Firewall {removed.get('name')} removido com sucesso!"})

    # PUT: Atualizar
    data = request.json or {}
    fw = firewalls[idx]
    if 'name' in data: fw['name'] = data['name'].strip()
    if 'host' in data: fw['host'] = data['host'].strip()
    if 'port' in data: fw['port'] = str(data['port']).strip()
    if 'city' in data: fw['city'] = data['city'].strip()
    if 'role' in data: fw['role'] = data['role'].strip()
    if 'location' in data: fw['location'] = data['location'].strip()
    if 'user' in data: fw['user'] = data['user'].strip()
    if 'password' in data and data['password']: fw['password'] = data['password']
    if 'use_default_auth' in data: fw['use_default_auth'] = bool(data['use_default_auth'])
    if 'enabled' in data: fw['enabled'] = bool(data['enabled'])

    firewalls[idx] = fw
    cfg['firewalls'] = firewalls
    ConfigService.save_config(cfg)
    return jsonify({'success': True, 'appliance': fw, 'message': 'Firewall atualizado com sucesso!'})

@inventory_bp.route('/api/firewall/appliances/test', methods=['POST'])
def test_firewall_connectivity():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    host = (data.get('host') or '').strip()
    port = int(data.get('port') or 4444)
    if not host:
        return jsonify({'success': False, 'error': 'IP do host é obrigatório'}), 400

    from app.services.wan_monitor_service import WanMonitorService
    probe = WanMonitorService._probe_icmp(host, count=2, timeout_sec=2)

    # Teste de porta TCP 4444
    import socket
    port_open = False
    sock_err = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((host, port))
        s.close()
        port_open = True
    except Exception as err:
        sock_err = str(err)

    return jsonify({
        'success': True,
        'host': host,
        'port': port,
        'ping': probe,
        'port_open': port_open,
        'port_error': sock_err,
        'summary': 'Online (Ping & Porta 4444 OK)' if (probe['alive'] and port_open) else (
            'Ping OK, mas Porta 4444 Fechada/Filtrada' if probe['alive'] else 'Sem Resposta (Host Inacessível / 100% perda)'
        )
    })

@inventory_bp.route('/api/firewall/wan-health', methods=['GET'])
def get_wan_health():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    from app.services.wan_monitor_service import WanMonitorService
    force = request.args.get('force', 'false').lower() == 'true'
    host = request.args.get('host')
    data = WanMonitorService.get_wan_health(force=force, host=host)
    return jsonify(data)

@inventory_bp.route('/api/firewall/wan-links', methods=['GET', 'POST'])
def manage_wan_links():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.config_service import ConfigService
    cfg = ConfigService.load_config()
    wan_links = cfg.get("wan_links", [])

    if request.method == 'GET':
        host = request.args.get('host')
        from app.services.wan_monitor_service import WanMonitorService
        links = WanMonitorService.get_links_for_host(host)
        return jsonify({'success': True, 'links': links})

    # POST: Criar novo link WAN
    data = request.json or {}
    name = (data.get('name') or '').strip()
    target_ip = (data.get('target_ip') or '').strip()
    appliance_host = (data.get('appliance_host') or '10.1.1.2').strip()

    if not name or not target_ip:
        return jsonify({'success': False, 'error': 'Nome do link e IP de teste são obrigatórios'}), 400

    import uuid
    link_id = data.get('id') or f"link-{uuid.uuid4().hex[:6]}"
    new_link = {
        "id": link_id,
        "appliance_host": appliance_host,
        "name": name,
        "provider": (data.get('provider') or 'Operadora').strip(),
        "interface_name": (data.get('interface_name') or 'PortWAN').strip(),
        "target_ip": target_ip,
        "source_ip": (data.get('source_ip') or '').strip(),
        "fallback_probes": data.get('fallback_probes') or [],
        "expected_speed": data.get('expected_speed') or '1000 Mbps - Full Duplex',
        "baseline_rtt_ms": float(data.get('baseline_rtt_ms') or 15.0),
        "type": data.get('type') or 'WAN'
    }

    wan_links.append(new_link)
    cfg["wan_links"] = wan_links
    ConfigService.save_config(cfg)
    from app.services.wan_monitor_service import WanMonitorService
    WanMonitorService.clear_cache()
    return jsonify({'success': True, 'link': new_link})

@inventory_bp.route('/api/firewall/wan-links/<link_id>', methods=['PUT', 'DELETE'])
def modify_wan_link(link_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.config_service import ConfigService
    cfg = ConfigService.load_config()
    wan_links = cfg.get("wan_links", [])

    idx = next((i for i, l in enumerate(wan_links) if l.get("id") == link_id), None)
    if idx is None:
        return jsonify({'success': False, 'error': f'Link {link_id} não encontrado'}), 404

    if request.method == 'DELETE':
        deleted = wan_links.pop(idx)
        cfg["wan_links"] = wan_links
        ConfigService.save_config(cfg)
        from app.services.wan_monitor_service import WanMonitorService
        WanMonitorService.clear_cache()
        return jsonify({'success': True, 'message': f'Link {link_id} removido com sucesso'})

    # PUT: Atualizar link
    data = request.json or {}
    link = wan_links[idx]
    if 'name' in data: link['name'] = data['name'].strip()
    if 'provider' in data: link['provider'] = data['provider'].strip()
    if 'interface_name' in data: link['interface_name'] = data['interface_name'].strip()
    if 'target_ip' in data: link['target_ip'] = data['target_ip'].strip()
    if 'source_ip' in data: link['source_ip'] = data['source_ip'].strip()
    if 'expected_speed' in data: link['expected_speed'] = data['expected_speed'].strip()
    if 'baseline_rtt_ms' in data: link['baseline_rtt_ms'] = float(data['baseline_rtt_ms'])
    if 'appliance_host' in data: link['appliance_host'] = data['appliance_host'].strip()
    if 'type' in data: link['type'] = data['type'].strip()

    wan_links[idx] = link
    cfg["wan_links"] = wan_links
    ConfigService.save_config(cfg)
    from app.services.wan_monitor_service import WanMonitorService
    WanMonitorService.clear_cache()
    return jsonify({'success': True, 'link': link})

@inventory_bp.route('/api/firewall/wan-links/test-single', methods=['POST'])
def test_single_wan_link():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    link_id = (data.get('link_id') or '').strip()
    host = (data.get('host') or '').strip()
    if not link_id:
        return jsonify({'success': False, 'error': 'ID do link é obrigatório'}), 400

    from app.services.wan_monitor_service import WanMonitorService
    result = WanMonitorService.probe_single_link(link_id, host=host)
    return jsonify(result)

@inventory_bp.route('/api/firewall/interfaces', methods=['GET'])
def get_firewall_interfaces():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    host = request.args.get('host')
    from app.services.sophos_service import SophosService
    ifaces = SophosService.get_all_interfaces_for_selection(host=host)
    return jsonify({'success': True, 'interfaces': ifaces})

@inventory_bp.route('/api/firewall/wan-links/extended-ping', methods=['POST'])
def run_extended_wan_ping():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    target_ip = (data.get('target_ip') or '').strip()
    link_id = (data.get('link_id') or '').strip()
    count = int(data.get('count') or 15)
    baseline_rtt = float(data.get('baseline_rtt_ms') or 15.0)
    host = (data.get('host') or '').strip()

    source_ip = None
    if link_id:
        from app.services.wan_monitor_service import WanMonitorService
        links = WanMonitorService.get_links_for_host(host)
        l = next((x for x in links if x.get('id') == link_id), None)
        if l:
            if not target_ip:
                target_ip = l.get('target_ip', '')
            baseline_rtt = float(l.get('baseline_rtt_ms', baseline_rtt))
            source_ip = l.get('source_ip')

    if not target_ip:
        return jsonify({'success': False, 'error': 'IP de destino ou link_id válido é obrigatório'}), 400

    from app.services.wan_monitor_service import WanMonitorService
    result = WanMonitorService.run_extended_ping(target_ip, count=count, baseline_rtt=baseline_rtt, source_ip=source_ip)
    return jsonify(result)

@inventory_bp.route('/api/firewall/wan-links/live-metrics', methods=['GET'])
def get_wan_live_metrics():
    """Retorna métricas em tempo real e histórico de telemetria dos links WAN."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    host = request.args.get('host')
    force = request.args.get('force') == 'true'
    from app.services.wan_monitor_service import WanMonitorService
    data = WanMonitorService.get_wan_health(force=force, host=host)
    return jsonify(data)

@inventory_bp.route('/api/firewall/wan-links/speedtest', methods=['POST'])
def run_wan_speedtest():
    """Executa teste de velocidade de download/upload com suporte a bind de IP de origem."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}
    link_id = (data.get('link_id') or '').strip()
    source_ip = (data.get('source_ip') or '').strip()
    server_id = (data.get('server_id') or '').strip()
    test_size_mb = int(data.get('test_size_mb') or 30)
    engine = (data.get('engine') or 'netlens').strip()

    # Se source_ip não foi passado diretamente, tentar obter da configuração do link
    if not source_ip and link_id:
        from app.services.wan_monitor_service import WanMonitorService
        links = WanMonitorService.get_links_for_host()
        l = next((x for x in links if x.get('id') == link_id), None)
        if l and l.get('source_ip'):
            source_ip = l.get('source_ip')

    from app.services.wan_speedtest_service import WanSpeedtestService
    if engine == 'ookla_cli':
        result = WanSpeedtestService.run_ookla_cli(
            link_id=link_id,
            source_ip=source_ip,
            server_id=server_id
        )
    else:
        result = WanSpeedtestService.run_speedtest(
            link_id=link_id,
            source_ip=source_ip,
            server_id=server_id,
            test_size_mb=test_size_mb
        )
    return jsonify(result)

@inventory_bp.route('/api/speedtest/servers', methods=['GET', 'POST'])
def handle_speedtest_servers():
    """Lista ou cadastra servidores de teste de velocidade de destino."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.wan_speedtest_service import WanSpeedtestService

    if request.method == 'GET':
        servers = WanSpeedtestService.get_servers()
        return jsonify({'success': True, 'servers': servers})

    # POST: Criar novo servidor
    data = request.json or {}
    try:
        new_srv = WanSpeedtestService.add_custom_server(data)
        return jsonify({'success': True, 'server': new_srv})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/speedtest/servers/<server_id>', methods=['DELETE'])
def delete_speedtest_server(server_id):
    """Exclui um servidor customizado de destino."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    from app.services.wan_speedtest_service import WanSpeedtestService
    deleted = WanSpeedtestService.delete_custom_server(server_id)
    if deleted:
        return jsonify({'success': True, 'message': 'Servidor removido com sucesso'})
    return jsonify({'success': False, 'error': 'Servidor não encontrado ou é interno (builtin)'}), 404



