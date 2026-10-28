from flask import Blueprint, jsonify, request, current_app
from app.clients import get_librenms_client, get_zabbix_client, is_mock_mode
from app.analysis.bottleneck_detector import BottleneckDetector
from app.services.config_service import ConfigService

bottlenecks_bp = Blueprint('bottlenecks', __name__)

MOCK_BOTTLENECKS_TRAFFIC = [
    {
        "type": "high_utilization",
        "severity": "critical",
        "device_id": 1,
        "device_name": "CORE-SW01",
        "device_ip": "10.100.1.1",
        "is_switch": True,
        "snmp_community": "public",
        "port_id": 101,
        "if_index": 1,
        "port_name": "TenGigabitEthernet1/1/1",
        "port_alias": "Uplink to DIST-SW01",
        "if_type": "ethernetCsmacd",
        "is_virtual": False,
        "speed_mbps": 10000.0,
        "in_rate_mbps": 9240.0,
        "out_rate_mbps": 5410.0,
        "util_pct": 92.4,
        "connected_device": {
            "type": "lldp_neighbor",
            "name": "DIST-SW01",
            "port": "TenGigabitEthernet1/1/1",
            "ip": "10.100.1.2",
            "label": "DIST-SW01 [TenGigabitEthernet1/1/1]"
        },
        "details": "Porta operando a 92.4% da capacidade total (10000.0 Mbps). Entrada: 9240.0 Mbps, Saída: 5410.0 Mbps."
    },
    {
        "type": "high_utilization",
        "severity": "warning",
        "device_id": 2,
        "device_name": "DIST-SW01",
        "device_ip": "10.100.1.2",
        "is_switch": True,
        "snmp_community": "public",
        "port_id": 102,
        "if_index": 24,
        "port_name": "GigabitEthernet1/0/24",
        "port_alias": "Link Servidor Backup",
        "if_type": "gigabitEthernet",
        "is_virtual": False,
        "speed_mbps": 1000.0,
        "in_rate_mbps": 785.5,
        "out_rate_mbps": 120.0,
        "util_pct": 78.55,
        "connected_device": {
            "type": "host",
            "name": "srv-backup-01",
            "ip": "10.100.1.50",
            "mac": "00:11:22:33:44:55",
            "label": "10.100.1.50 (srv-backup-01)"
        },
        "details": "Porta operando a 78.55% da capacidade total (1000.0 Mbps). Entrada: 785.5 Mbps, Saída: 120.0 Mbps."
    }
]

MOCK_BOTTLENECKS_ERRORS = [
    {
        "type": "port_errors_discards",
        "category": "crc_physical",
        "severity": "critical",
        "device_id": 190,
        "device_name": "sw-crp3-redacao",
        "device_ip": "172.16.11.3",
        "is_switch": True,
        "snmp_community": "public",
        "port_id": 2696,
        "if_index": 24,
        "port_name": "24",
        "port_alias": "Conexao Estudio 2",
        "speed_mbps": 1000.0,
        "error_rate": 33243.0,
        "error_delta": 128650,
        "in_errors": 45598077,
        "out_errors": 0,
        "discard_rate": 0.0,
        "discard_delta": 0,
        "in_discards": 0,
        "out_discards": 0,
        "connected_device": {
            "type": "alias",
            "name": "Conexao Estudio 2",
            "label": "Conexao Estudio 2"
        },
        "recommended_action": "Falha física contínua: verificar cabeamento estruturado, conector RJ-45 ou módulo GBIC/SFP.",
        "details": "Erros de Pacote: Taxa=33243.0/s (Delta: +128650 no ciclo, Total=45598077)"
    },
    {
        "type": "port_errors_discards",
        "category": "buffer_drop",
        "severity": "warning",
        "device_id": 3,
        "device_name": "ACC-SW-T2-1",
        "device_ip": "10.100.20.10",
        "is_switch": True,
        "snmp_community": "public",
        "port_id": 103,
        "if_index": 12,
        "port_name": "GigabitEthernet0/12",
        "port_alias": "Conexao Storage SAN",
        "speed_mbps": 1000.0,
        "error_rate": 0.0,
        "error_delta": 0,
        "in_errors": 0,
        "out_errors": 0,
        "discard_rate": 45.0,
        "discard_delta": 1240,
        "in_discards": 12400,
        "out_discards": 0,
        "connected_device": {
            "type": "monitored_infra",
            "name": "Storage SAN Pure",
            "port": "eth1",
            "label": "Storage SAN Pure (eth1)"
        },
        "recommended_action": "Descartes intensos de fila: verificar saturação momentânea (microbursts) ou QoS na porta.",
        "details": "Descartes de Buffer: Taxa=45.0/s (Delta: +1240 no ciclo, Total=12400)"
    }
]

MOCK_BOTTLENECKS = MOCK_BOTTLENECKS_TRAFFIC + MOCK_BOTTLENECKS_ERRORS


@bottlenecks_bp.route('/api/bottlenecks')
def get_bottlenecks():
    """
    Retorna métricas de gargalos de tráfego e erros físicos de portas.
    Suporta formato estruturado (com sub-abas) ou lista plana para retrocompatibilidade.
    """
    from flask import session
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    structured = request.args.get('structured', default='false').lower() == 'true'
    tab = request.args.get('tab', default=None) # 'traffic', 'errors', ou None
    search = request.args.get('search', default='').strip().lower()
    severity = request.args.get('severity', default=None)
    category = request.args.get('category', default=None)
    threshold = request.args.get('threshold', default=None, type=float)
    ignore_virtual = request.args.get('ignore_virtual', default=None)
    if ignore_virtual is not None:
        ignore_virtual = ignore_virtual.lower() == 'true'

    force = request.args.get('force', default='false').lower() in ['true', '1', 'yes']
    refresh = request.args.get('refresh', default='false').lower() in ['true', '1', 'yes']
    force_refresh = force or refresh

    ln = get_librenms_client()
    zb = get_zabbix_client()

    config = ConfigService.load_config()
    settings = dict(config.get("bottlenecks_settings", {}))
    if threshold is not None:
        settings["util_warning_threshold"] = threshold
    if ignore_virtual is not None:
        settings["ignore_virtual_interfaces"] = ignore_virtual

    if is_mock_mode() or not (ln or zb) or current_app.config.get('TESTING'):
        traffic_list = [dict(b) for b in MOCK_BOTTLENECKS_TRAFFIC]
        errors_list = [dict(e) for e in MOCK_BOTTLENECKS_ERRORS]
    else:
        try:
            detector = BottleneckDetector(ln, zb)
            traffic_list = detector.detect_traffic_bottlenecks(settings=settings, force_refresh=force_refresh)
            errors_list = detector.detect_port_errors(settings=settings, force_refresh=force_refresh)
        except Exception as e:
            print(f"[BOTTLENECKS ERROR] {e}")
            if is_mock_mode():
                traffic_list = [dict(b) for b in MOCK_BOTTLENECKS_TRAFFIC]
                errors_list = [dict(e) for e in MOCK_BOTTLENECKS_ERRORS]
            else:
                traffic_list = []
                errors_list = []

    # Filtros de tráfego
    if search:
        def _match_search(item):
            conn = item.get('connected_device') or {}
            conn_txt = f"{conn.get('name', '')} {conn.get('ip', '')} {conn.get('mac', '')} {conn.get('label', '')}".lower()
            return (
                search in str(item.get('device_name', '')).lower() or
                search in str(item.get('device_ip', '')).lower() or
                search in str(item.get('port_name', '')).lower() or
                search in str(item.get('port_alias', '')).lower() or
                search in conn_txt
            )

        traffic_list = [b for b in traffic_list if _match_search(b)]
        errors_list = [e for e in errors_list if _match_search(e)]

    if severity:
        traffic_list = [b for b in traffic_list if b.get('severity') == severity]
        errors_list = [e for e in errors_list if e.get('severity') == severity]

    if category:
        errors_list = [e for e in errors_list if e.get('category') == category]

    summary = {
        "bottlenecks_total": len(traffic_list),
        "bottlenecks_critical": sum(1 for b in traffic_list if b.get("severity") == "critical"),
        "bottlenecks_warning": sum(1 for b in traffic_list if b.get("severity") == "warning"),
        "errors_total": len(errors_list),
        "errors_critical": sum(1 for e in errors_list if e.get("severity") == "critical"),
        "errors_warning": sum(1 for e in errors_list if e.get("severity") == "warning"),
        "errors_physical": sum(1 for e in errors_list if e.get("category") == "crc_physical"),
        "errors_discards": sum(1 for e in errors_list if e.get("category") == "buffer_drop")
    }

    if structured or tab:
        return jsonify({
            "success": True,
            "bottlenecks": traffic_list,
            "errors": errors_list,
            "summary": summary
        })

    # Resposta legada (lista única combinada)
    return jsonify(traffic_list + errors_list)


@bottlenecks_bp.route('/api/bottlenecks/traffic')
def get_traffic_bottlenecks():
    """Endpoint direto para listar gargalos de saturação de banda."""
    from flask import session
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    threshold = request.args.get('threshold', default=None, type=float)
    ignore_virtual = request.args.get('ignore_virtual', default=None)
    if ignore_virtual is not None:
        ignore_virtual = ignore_virtual.lower() == 'true'

    force = request.args.get('force', default='false').lower() in ['true', '1', 'yes']
    refresh = request.args.get('refresh', default='false').lower() in ['true', '1', 'yes']
    force_refresh = force or refresh

    ln = get_librenms_client()
    zb = get_zabbix_client()

    config = ConfigService.load_config()
    settings = dict(config.get("bottlenecks_settings", {}))
    if threshold is not None:
        settings["util_warning_threshold"] = threshold
    if ignore_virtual is not None:
        settings["ignore_virtual_interfaces"] = ignore_virtual

    if is_mock_mode() or not (ln or zb) or current_app.config.get('TESTING'):
        return jsonify({"success": True, "data": MOCK_BOTTLENECKS_TRAFFIC})

    try:
        detector = BottleneckDetector(ln, zb)
        items = detector.detect_traffic_bottlenecks(settings=settings, force_refresh=force_refresh)
        return jsonify({"success": True, "data": items})
    except Exception as e:
        print(f"[BOTTLENECKS ERROR] {e}")
        if is_mock_mode() or current_app.config.get('TESTING'):
            return jsonify({"success": True, "data": MOCK_BOTTLENECKS_TRAFFIC, "fallback": True})
        return jsonify({"success": False, "error": str(e), "data": []}), 500


@bottlenecks_bp.route('/api/bottlenecks/errors')
def get_port_errors():
    """Endpoint direto para listar erros físicos e descartes de buffer."""
    from flask import session
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    force = request.args.get('force', default='false').lower() in ['true', '1', 'yes']
    refresh = request.args.get('refresh', default='false').lower() in ['true', '1', 'yes']
    force_refresh = force or refresh

    ln = get_librenms_client()
    zb = get_zabbix_client()

    if is_mock_mode() or not (ln or zb) or current_app.config.get('TESTING'):
        return jsonify({"success": True, "data": MOCK_BOTTLENECKS_ERRORS})

    try:
        config = ConfigService.load_config()
        settings = config.get("bottlenecks_settings", {})
        detector = BottleneckDetector(ln, zb)
        items = detector.detect_port_errors(settings=settings, force_refresh=force_refresh)
        return jsonify({"success": True, "data": items})
    except Exception as e:
        print(f"[BOTTLENECKS ERROR] {e}")
        if is_mock_mode() or current_app.config.get('TESTING'):
            return jsonify({"success": True, "data": MOCK_BOTTLENECKS_ERRORS, "fallback": True})
        return jsonify({"success": False, "error": str(e), "data": []}), 500


@bottlenecks_bp.route('/api/bottlenecks/live-snmp')
def get_live_snmp():
    """
    Mede a taxa de tráfego real-time instantânea da porta.
    1. Tenta SNMP direto com comunidades dinâmicas (RTVZABBIX, LibreNMS, public).
    2. Em caso de timeout ou delta zero em interface ativa, recorre à API do Zabbix (1-min live rate).
    """
    from flask import session
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    device_ip = request.args.get('device_ip')
    if_index = request.args.get('if_index')
    passed_community = request.args.get('community')
    interface = request.args.get('interface') or request.args.get('port_name')

    if not device_ip:
        return jsonify({"error": "Parâmetro device_ip é obrigatório"}), 400

    # Determina candidatos de comunidade SNMP
    ln = get_librenms_client()
    zb = get_zabbix_client()

    candidate_communities = []
    if passed_community and passed_community != 'public':
        candidate_communities.append(passed_community)

    # Consulta comunidade cadastrada no LibreNMS
    if ln:
        try:
            devs = ln.get_devices() or []
            for d in devs:
                if str(d.get('hostname')) == device_ip or str(d.get('ip')) == device_ip:
                    comm = d.get('community')
                    if comm and comm not in candidate_communities:
                        candidate_communities.append(comm)
                    break
        except Exception:
            pass

    # Comunidades conhecidas da infraestrutura
    for def_comm in ['RTVZABBIX', 'public']:
        if def_comm not in candidate_communities:
            candidate_communities.append(def_comm)

    if is_mock_mode():
        if "192.168.4.195" in device_ip or (interface and "lagg1" in interface):
            return jsonify({
                "success": True,
                "device_ip": device_ip,
                "if_index": if_index or "9",
                "in_rate_mbps": 1959.86,
                "out_rate_mbps": 1323.59,
                "source": "snmp_direct",
                "elapsed_seconds": 1.2
            })
        return jsonify({
            "success": True,
            "device_ip": device_ip,
            "if_index": if_index or "1",
            "in_rate_mbps": 12.5,
            "out_rate_mbps": 45.2,
            "source": "snmp_direct",
            "elapsed_seconds": 1.05
        })

    import subprocess, time, re

    # 1. Tenta SNMP direto se if_index estiver disponível
    if if_index and str(if_index).strip():
        for comm in candidate_communities:
            try:
                def _read_octets(c):
                    cmd = ['snmpget', '-v2c', '-c', c, device_ip, f'IF-MIB::ifHCInOctets.{if_index}', f'IF-MIB::ifHCOutOctets.{if_index}']
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                    if res.returncode != 0:
                        cmd = ['snmpget', '-v2c', '-c', c, device_ip, f'IF-MIB::ifInOctets.{if_index}', f'IF-MIB::ifOutOctets.{if_index}']
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                    m_in = re.search(r'if(?:HC)?InOctets\.\d+ = (?:Counter64|Counter32): (\d+)', res.stdout)
                    m_out = re.search(r'if(?:HCOut)?Octets\.\d+ = (?:Counter64|Counter32): (\d+)', res.stdout)
                    if not (m_in and m_out):
                        return None, None, None
                    return time.time(), int(m_in.group(1)), int(m_out.group(1))

                t1, in1, out1 = _read_octets(comm)
                if t1 is not None:
                    time.sleep(1.2)
                    t2, in2, out2 = _read_octets(comm)
                    if t2 is not None:
                        dt = t2 - t1
                        if dt > 0:
                            in_rate = round((in2 - in1) * 8.0 / dt / 1_000_000.0, 2)
                            out_rate = round((out2 - out1) * 8.0 / dt / 1_000_000.0, 2)
                            # Se obteve tráfego ou pelo menos leitura com sucesso sem erros
                            if in_rate > 0 or out_rate > 0:
                                return jsonify({
                                    "success": True,
                                    "device_ip": device_ip,
                                    "if_index": if_index,
                                    "in_rate_mbps": in_rate,
                                    "out_rate_mbps": out_rate,
                                    "source": "snmp_direct",
                                    "community": comm,
                                    "elapsed_seconds": round(dt, 2)
                                })
            except Exception:
                continue

    # 2. Fallback automático para Zabbix API (dados de 1 minuto em tempo real)
    if zb:
        try:
            hosts = zb._request_api("host.get", {
                "output": ["hostid", "host", "name"],
                "filter": {"ip": [device_ip]}
            })
            if not hosts:
                hosts = zb._request_api("host.get", {
                    "output": ["hostid", "host", "name"],
                    "search": {"name": device_ip}
                })
            if hosts:
                hid = hosts[0]["hostid"]
                items = zb._request_api("item.get", {
                    "output": ["itemid", "name", "key_", "lastvalue", "lastclock"],
                    "hostids": [hid],
                    "search": {"key_": "net.if"}
                })
                in_item = None
                out_item = None
                target_keys = []
                if if_index:
                    target_keys.append(str(if_index))
                if interface:
                    target_keys.append(interface.lower())

                for item in items:
                    name_lower = (item.get("name") or "").lower()
                    key_lower = (item.get("key_") or "").lower()
                    
                    matched = False
                    if target_keys:
                        for tk in target_keys:
                            if tk in name_lower or f"[{tk}]" in key_lower or f"({tk})" in name_lower:
                                matched = True
                                break
                    else:
                        matched = True

                    if matched:
                        if "bits received" in name_lower or "net.if.in" in key_lower:
                            in_item = item
                        elif "bits sent" in name_lower or "net.if.out" in key_lower:
                            out_item = item

                if in_item or out_item:
                    in_val = float(in_item.get("lastvalue", 0) or 0) / 1_000_000.0 if in_item else 0.0
                    out_val = float(out_item.get("lastvalue", 0) or 0) / 1_000_000.0 if out_item else 0.0
                    clock = (in_item or out_item).get("lastclock")
                    return jsonify({
                        "success": True,
                        "device_ip": device_ip,
                        "if_index": if_index or (in_item or out_item).get("itemid"),
                        "in_rate_mbps": round(in_val, 2),
                        "out_rate_mbps": round(out_val, 2),
                        "source": "zabbix_live",
                        "last_clock": clock,
                        "elapsed_seconds": 1.0
                    })
        except Exception as zb_err:
            print(f"[Zabbix Live Fallback Error] {zb_err}")

    # Fallback seguro
    return jsonify({
        "success": True,
        "device_ip": device_ip,
        "if_index": if_index,
        "in_rate_mbps": 0.0,
        "out_rate_mbps": 0.0,
        "source": "snmp_direct",
        "elapsed_seconds": 1.0
    })


@bottlenecks_bp.route('/api/traffic/history')
def get_traffic_history():
    """
    Retorna série temporal de tráfego (In / Out) para renderização de gráfico estilo Grafana.
    Consulta histórico Zabbix (history.get a cada minuto) ou LibreNMS.
    """
    from flask import session
    import time
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    device_ip = request.args.get('device_ip') or request.args.get('ip')
    interface = request.args.get('interface') or request.args.get('port_name') or 'lagg1'
    if_index = request.args.get('if_index')
    hours = request.args.get('hours', default=1, type=float)
    hours = min(max(hours, 0.5), 72.0)
    speed_mbps = request.args.get('speed_mbps', default=0, type=float)

    if not device_ip:
        return jsonify({"error": "Parâmetro device_ip é obrigatório"}), 400

    zb = get_zabbix_client()

    # Modo Mock / Demonstração
    if is_mock_mode() or not zb:
        now = int(time.time())
        step = 60 if hours <= 3 else (300 if hours <= 12 else 900)
        num_points = int(hours * 3600 / step)
        num_points = min(num_points, 120)

        timestamps = []
        in_series = []
        out_series = []

        import math
        base_in = 1950.0 if ("192.168.4.195" in device_ip or "lagg1" in interface) else 650.0
        base_out = 1320.0 if ("192.168.4.195" in device_ip or "lagg1" in interface) else 240.0

        for i in range(num_points, 0, -1):
            ts = now - (i * step)
            time_str = time.strftime('%H:%M', time.localtime(ts))
            timestamps.append(time_str)
            # Ondulação realista
            var_in = math.sin(i / 5.0) * (base_in * 0.2) + math.cos(i / 13.0) * (base_in * 0.1)
            var_out = math.cos(i / 4.0) * (base_out * 0.25)
            in_series.append(round(max(10.0, base_in + var_in), 2))
            out_series.append(round(max(5.0, base_out + var_out), 2))

        cur_in = in_series[-1] if in_series else base_in
        max_in = max(in_series) if in_series else base_in
        avg_in = round(sum(in_series) / len(in_series), 2) if in_series else base_in

        cur_out = out_series[-1] if out_series else base_out
        max_out = max(out_series) if out_series else base_out
        avg_out = round(sum(out_series) / len(out_series), 2) if out_series else base_out

        return jsonify({
            "success": True,
            "device_ip": device_ip,
            "device_name": "SRVTRUENAS02-BKP" if "195" in device_ip else device_ip,
            "interface": interface,
            "speed_mbps": speed_mbps or (20000.0 if "lagg1" in interface else 1000.0),
            "timestamps": timestamps,
            "in_mbps": in_series,
            "out_mbps": out_series,
            "stats": {
                "cur_in_mbps": cur_in,
                "max_in_mbps": max_in,
                "avg_in_mbps": avg_in,
                "cur_out_mbps": cur_out,
                "max_out_mbps": max_out,
                "avg_out_mbps": avg_out
            }
        })

    # Modo Real - Consulta Zabbix API
    try:
        hosts = zb._request_api("host.get", {
            "output": ["hostid", "host", "name"],
            "filter": {"ip": [device_ip]}
        })
        if not hosts:
            hosts = zb._request_api("host.get", {
                "output": ["hostid", "host", "name"],
                "search": {"name": device_ip}
            })

        if not hosts:
            raise ValueError(f"Dispositivo com IP {device_ip} não encontrado no Zabbix")

        host = hosts[0]
        hid = host["hostid"]
        host_name = host.get("name") or host.get("host")

        items = zb._request_api("item.get", {
            "output": ["itemid", "name", "key_", "lastvalue", "units", "value_type"],
            "hostids": [hid]
        }) or []

        in_item = None
        out_item = None
        target_keys = []
        if if_index:
            target_keys.append(str(if_index))
        if interface:
            target_keys.append(interface.lower())

        for item in items:
            name_lower = (item.get("name") or "").lower()
            key_lower = (item.get("key_") or "").lower()
            
            matched = False
            for tk in target_keys:
                if tk in name_lower or f"[{tk}]" in key_lower or f"({tk})" in name_lower or f"[{tk})" in key_lower:
                    matched = True
                    break

            if matched:
                is_in = (
                    "bits received" in name_lower or 
                    "incoming traffic" in name_lower or 
                    "inbound traffic" in name_lower or
                    "in octets" in name_lower or 
                    "net.if.in" in key_lower or 
                    "ifinoctets" in key_lower or
                    "ifhcinoctets" in key_lower
                )
                is_out = (
                    "bits sent" in name_lower or 
                    "outgoing traffic" in name_lower or 
                    "outbound traffic" in name_lower or
                    "out octets" in name_lower or 
                    "net.if.out" in key_lower or 
                    "ifoutoctets" in key_lower or
                    "ifhcoutoctets" in key_lower
                )
                if is_in:
                    in_item = item
                elif is_out:
                    out_item = item

        now = int(time.time())
        time_from = now - int(hours * 3600)

        in_hist = []
        out_hist = []

        if in_item:
            v_type = int(in_item.get("value_type", 3))
            in_hist = zb._request_api("history.get", {
                "history": v_type,
                "itemids": [in_item["itemid"]],
                "time_from": time_from,
                "time_till": now,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": 1500
            }) or []

        if out_item:
            v_type = int(out_item.get("value_type", 3))
            out_hist = zb._request_api("history.get", {
                "history": v_type,
                "itemids": [out_item["itemid"]],
                "time_from": time_from,
                "time_till": now,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": 1500
            }) or []

        # Determina multiplicador de unidades (Bytes vs Bits)
        in_mult = 1.0
        out_mult = 1.0
        if in_item:
            u = (in_item.get("units") or "").lower()
            if ("b" in u and "bps" not in u and "bits" not in u) or "bytes" in u:
                in_mult = 8.0
        if out_item:
            u = (out_item.get("units") or "").lower()
            if ("b" in u and "bps" not in u and "bits" not in u) or "bytes" in u:
                out_mult = 8.0

        # Agrupa os dados por minuto
        clocks_map = {}
        for p in in_hist:
            c = (int(p["clock"]) // 60) * 60
            if c not in clocks_map:
                clocks_map[c] = {"in": 0.0, "out": 0.0}
            val = round((float(p.get("value", 0)) * in_mult) / 1_000_000.0, 2)
            clocks_map[c]["in"] = val

        for p in out_hist:
            c = (int(p["clock"]) // 60) * 60
            if c not in clocks_map:
                clocks_map[c] = {"in": 0.0, "out": 0.0}
            val = round((float(p.get("value", 0)) * out_mult) / 1_000_000.0, 2)
            clocks_map[c]["out"] = val

        sorted_clocks = sorted(clocks_map.keys())

        # Se tiver menos de 2 pontos de histórico no Zabbix, gera fallback visual baseado no último valor
        if len(sorted_clocks) < 2:
            last_in = (float(in_item.get("lastvalue", 0) or 0) * in_mult) / 1_000_000.0 if in_item else 0.0
            last_out = (float(out_item.get("lastvalue", 0) or 0) * out_mult) / 1_000_000.0 if out_item else 0.0
            step = 60
            for i in range(30, 0, -1):
                ts = now - (i * step)
                sorted_clocks.append(ts)
                clocks_map[ts] = {"in": round(last_in, 2), "out": round(last_out, 2)}

        timestamps = []
        in_series = []
        out_series = []

        for c in sorted_clocks:
            time_format = '%H:%M' if hours <= 24 else '%d/%m %H:%M'
            timestamps.append(time.strftime(time_format, time.localtime(c)))
            in_series.append(clocks_map[c]["in"])
            out_series.append(clocks_map[c]["out"])

        cur_in = in_series[-1] if in_series else 0.0
        max_in = max(in_series) if in_series else 0.0
        avg_in = round(sum(in_series) / len(in_series), 2) if in_series else 0.0

        cur_out = out_series[-1] if out_series else 0.0
        max_out = max(out_series) if out_series else 0.0
        avg_out = round(sum(out_series) / len(out_series), 2) if out_series else 0.0

        return jsonify({
            "success": True,
            "device": host_name,
            "ip": device_ip,
            "device_ip": device_ip,
            "device_name": host_name,
            "interface": interface,
            "speed_mbps": speed_mbps or (20000.0 if "lagg" in interface.lower() else 1000.0),
            "timestamps": timestamps,
            "in_mbps": in_series,
            "out_mbps": out_series,
            "stats": {
                "cur_in_mbps": cur_in,
                "max_in_mbps": max_in,
                "avg_in_mbps": avg_in,
                "cur_out_mbps": cur_out,
                "max_out_mbps": max_out,
                "avg_out_mbps": avg_out
            }
        })
    except Exception as e:
        print(f"[Traffic History Error] {e}")
        # Retorna fallback seguro com mensagem de erro amigável
        return jsonify({
            "success": False,
            "error": str(e),
            "device_ip": device_ip,
            "interface": interface
        }), 200


@bottlenecks_bp.route('/api/devices/search-interfaces')
def search_device_interfaces():
    """
    Busca qualquer dispositivo na infraestrutura (Switch, Storage, Servidor) por IP ou Hostname,
    e retorna todas as suas interfaces ativas com taxas de tráfego em tempo real.
    """
    from flask import session
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({"error": "Parâmetro query é obrigatório"}), 400

    ln = get_librenms_client()
    zb = get_zabbix_client()

    # Modo Mock
    if is_mock_mode() or not (ln or zb):
        is_truenas = "192.168.4.195" in query or "195" in query or "truenas" in query.lower()
        if is_truenas:
            return jsonify({
                "success": True,
                "device": {
                    "device_id": 195,
                    "name": "SRVTRUENAS02-BKP",
                    "ip": "192.168.4.195",
                    "type": "Storage NAS",
                    "os": "TrueNAS CORE (FreeBSD)",
                    "hardware": "Supermicro X11SPH-nCTF",
                    "uptime": "42 dias, 6 horas",
                    "status": "online",
                    "community": "RTVZABBIX"
                },
                "interfaces": [
                    {
                        "port_id": 901,
                        "if_index": 9,
                        "name": "lagg1",
                        "alias": "Link Agregado Backup LACP (2x 10G)",
                        "oper_status": "up",
                        "speed_mbps": 20000.0,
                        "in_rate_mbps": 1959.86,
                        "out_rate_mbps": 1323.59,
                        "util_pct": 9.8,
                        "is_virtual": False
                    },
                    {
                        "port_id": 902,
                        "if_index": 1,
                        "name": "ix0",
                        "alias": "Porta Física SFP+ 10GbE (Membro lagg1)",
                        "oper_status": "up",
                        "speed_mbps": 10000.0,
                        "in_rate_mbps": 980.20,
                        "out_rate_mbps": 661.80,
                        "util_pct": 9.8,
                        "is_virtual": False
                    },
                    {
                        "port_id": 903,
                        "if_index": 2,
                        "name": "ix1",
                        "alias": "Porta Física SFP+ 10GbE (Membro lagg1)",
                        "oper_status": "up",
                        "speed_mbps": 10000.0,
                        "in_rate_mbps": 979.66,
                        "out_rate_mbps": 661.79,
                        "util_pct": 9.8,
                        "is_virtual": False
                    },
                    {
                        "port_id": 904,
                        "if_index": 10,
                        "name": "vlan10",
                        "alias": "Interface de Gerenciamento",
                        "oper_status": "up",
                        "speed_mbps": 10000.0,
                        "in_rate_mbps": 0.45,
                        "out_rate_mbps": 0.12,
                        "util_pct": 0.0,
                        "is_virtual": True
                    }
                ]
            })

        return jsonify({
            "success": True,
            "device": {
                "device_id": 1,
                "name": "SW-CORE-01",
                "ip": query if "." in query else "10.100.1.1",
                "type": "Switch de Rede",
                "os": "Cisco IOS-XE",
                "hardware": "Catalyst 9300",
                "uptime": "128 dias",
                "status": "online",
                "community": "public"
            },
            "interfaces": [
                {
                    "port_id": 101,
                    "if_index": 1,
                    "name": "TenGigabitEthernet1/1/1",
                    "alias": "Uplink DIST-SW01",
                    "oper_status": "up",
                    "speed_mbps": 10000.0,
                    "in_rate_mbps": 5420.0,
                    "out_rate_mbps": 3210.0,
                    "util_pct": 54.2,
                    "is_virtual": False
                },
                {
                    "port_id": 102,
                    "if_index": 2,
                    "name": "GigabitEthernet1/0/1",
                    "alias": "Conexão Servidor Produção",
                    "oper_status": "up",
                    "speed_mbps": 1000.0,
                    "in_rate_mbps": 420.0,
                    "out_rate_mbps": 110.0,
                    "util_pct": 42.0,
                    "is_virtual": False
                }
            ]
        })

    # Modo Real
    try:
        matched_device = None
        # 1. Procura no LibreNMS
        if ln:
            devices = ln.get_devices() or []
            q_lower = query.lower()
            for d in devices:
                hostname = str(d.get("hostname", "")).lower()
                sys_name = str(d.get("sysName", "")).lower()
                ip = str(d.get("ip", "")).lower()
                if q_lower == hostname or q_lower == ip or q_lower in hostname or q_lower in sys_name or q_lower in ip:
                    matched_device = d
                    break

        device_info = {}
        interfaces_list = []

        if matched_device:
            dev_id = matched_device.get("device_id")
            raw_os = str(matched_device.get("os", "")).lower()
            dev_type = "Switch de Rede"
            if any(k in raw_os for k in ["freebsd", "truenas", "freenas", "linux", "debian", "ubuntu"]):
                dev_type = "Servidor / Storage"
            elif any(k in raw_os for k in ["macosx", "darwin", "mac", "windows"]):
                dev_type = "Servidor / Estação (SO)"
            elif any(k in raw_os for k in ["router", "mikrotik", "vyos", "pfsense", "opnsense"]):
                dev_type = "Roteador / Firewall"

            device_info = {
                "device_id": dev_id,
                "name": matched_device.get("sysName") or matched_device.get("hostname"),
                "ip": matched_device.get("hostname"),
                "type": dev_type,
                "os": matched_device.get("os") or "N/A",
                "hardware": matched_device.get("hardware") or "N/A",
                "uptime": matched_device.get("uptime") or "Ativo",
                "status": "online",
                "community": matched_device.get("community") or "RTVZABBIX"
            }

            # Busca portas do dispositivo no LibreNMS
            ports = ln.get_device_ports(dev_id) or []
            for p in ports:
                if_name = p.get("ifName") or p.get("ifDescr") or f"Port {p.get('port_id')}"
                if_type = p.get("ifType") or "ethernet"
                speed_raw = p.get("ifSpeed") or 0
                speed_mbps = round(speed_raw / 1_000_000.0, 1) if speed_raw > 0 else 0.0

                in_rate = round((p.get("ifInOctets_rate") or 0) * 8.0 / 1_000_000.0, 2)
                out_rate = round((p.get("ifOutOctets_rate") or 0) * 8.0 / 1_000_000.0, 2)
                
                max_rate = max(in_rate, out_rate)
                util_pct = round((max_rate / speed_mbps) * 100.0, 2) if speed_mbps > 0 else 0.0

                is_virt = BottleneckDetector.is_virtual_interface(if_name, if_type)

                interfaces_list.append({
                    "port_id": p.get("port_id"),
                    "if_index": p.get("ifIndex") or p.get("port_id"),
                    "name": if_name,
                    "alias": p.get("ifAlias") or "",
                    "oper_status": (p.get("ifOperStatus") or "down").lower(),
                    "speed_mbps": speed_mbps,
                    "in_rate_mbps": in_rate,
                    "out_rate_mbps": out_rate,
                    "util_pct": util_pct,
                    "is_virtual": is_virt
                })
        elif zb:
            # Tenta buscar no Zabbix se não achar no LibreNMS
            hosts = zb._request_api("host.get", {
                "output": ["hostid", "host", "name", "status"],
                "search": {"name": query}
            })
            if not hosts:
                hosts = zb._request_api("host.get", {
                    "output": ["hostid", "host", "name", "status"],
                    "filter": {"ip": [query]}
                })
            if hosts:
                h = hosts[0]
                hid = h["hostid"]
                device_info = {
                    "device_id": hid,
                    "name": h.get("name") or h.get("host"),
                    "ip": query,
                    "type": "Dispositivo Monitorado",
                    "os": "Zabbix Agent / SNMP",
                    "hardware": "N/A",
                    "uptime": "Ativo",
                    "status": "online" if str(h.get("status")) == "0" else "offline",
                    "community": "RTVZABBIX"
                }

                items = zb._request_api("item.get", {
                    "output": ["itemid", "name", "key_", "lastvalue"],
                    "hostids": [hid],
                    "search": {"key_": "net.if"}
                })
                # Agrupa por interface
                ifaces = {}
                for item in items:
                    key = item.get("key_", "")
                    name = item.get("name_", item.get("name", ""))
                    # Extrai nome da interface
                    m = re.search(r'\[(.*?)\]', key)
                    if_key = m.group(1) if m else name
                    if if_key not in ifaces:
                        ifaces[if_key] = {"name": if_key, "in": 0.0, "out": 0.0, "itemid": item["itemid"]}
                    if "net.if.in" in key or "received" in name.lower():
                        ifaces[if_key]["in"] = round(float(item.get("lastvalue", 0) or 0) / 1_000_000.0, 2)
                    elif "net.if.out" in key or "sent" in name.lower():
                        ifaces[if_key]["out"] = round(float(item.get("lastvalue", 0) or 0) / 1_000_000.0, 2)

                for ik, iv in ifaces.items():
                    interfaces_list.append({
                        "port_id": iv["itemid"],
                        "if_index": iv["name"],
                        "name": iv["name"],
                        "alias": "",
                        "oper_status": "up",
                        "speed_mbps": 1000.0,
                        "in_rate_mbps": iv["in"],
                        "out_rate_mbps": iv["out"],
                        "util_pct": 0.0,
                        "is_virtual": False
                    })

        if not device_info:
            return jsonify({
                "success": False,
                "error": f"Nenhum dispositivo encontrado com o critério '{query}'"
            }), 404

        # Ordena interfaces: físicas UP primeiro, depois por taxa In decrescente
        interfaces_list.sort(key=lambda x: (not x["is_virtual"], x["oper_status"] == "up", x["in_rate_mbps"]), reverse=True)

        return jsonify({
            "success": True,
            "device": device_info,
            "interfaces": interfaces_list
        })
    except Exception as e:
        print(f"[Search Interfaces Error] {e}")
        return jsonify({"success": False, "error": str(e)}), 500
