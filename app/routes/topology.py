from flask import Blueprint, jsonify, request
from app.clients import get_netdisco_client, get_librenms_client, is_mock_mode
from app.analysis.path_tracer import PathTracer
from app.analysis.topology_tracker import TopologyTracker
from app.analysis.stp_tracker import StpTracker

topology_bp = Blueprint('topology', __name__)

MOCK_DEVICES = [
    {"ip": "10.100.1.1", "name": "CORE-SW01", "type": "Core Switch"},
    {"ip": "10.100.1.2", "name": "DIST-SW01", "type": "Distribution Switch"},
    {"ip": "10.100.1.3", "name": "DIST-SW02", "type": "Distribution Switch"},
    {"ip": "10.100.10.10", "name": "ACC-SW-T1-1", "type": "Access Switch"},
    {"ip": "10.100.10.11", "name": "ACC-SW-T1-2", "type": "Access Switch"},
    {"ip": "10.100.20.10", "name": "ACC-SW-T2-1", "type": "Access Switch"},
    {"ip": "10.100.20.11", "name": "ACC-SW-T2-2", "type": "Access Switch"},
    {"ip": "10.11.3.1", "name": "GW-BORDA01", "type": "Router L3"}
]

MOCK_LINKS = [
    {"from_device": "10.11.3.1", "from_device_name": "GW-BORDA01", "from_port": "eth0", "to_device": "10.100.1.1", "to_port": "GigabitEthernet1/0/24", "to_device_name": "CORE-SW01"},
    {"from_device": "10.100.1.1", "from_device_name": "CORE-SW01", "from_port": "TenGigabitEthernet1/1/1", "to_device": "10.100.1.2", "to_port": "TenGigabitEthernet1/1/1", "to_device_name": "DIST-SW01"},
    {"from_device": "10.100.1.1", "from_device_name": "CORE-SW01", "from_port": "TenGigabitEthernet1/1/2", "to_device": "10.100.1.3", "to_port": "TenGigabitEthernet1/1/1", "to_device_name": "DIST-SW02"},
    {"from_device": "10.100.1.2", "from_device_name": "DIST-SW01", "from_port": "GigabitEthernet1/0/1", "to_device": "10.100.10.10", "to_port": "GigabitEthernet0/1", "to_device_name": "ACC-SW-T1-1"},
    {"from_device": "10.100.1.2", "from_device_name": "DIST-SW01", "from_port": "GigabitEthernet1/0/2", "to_device": "10.100.10.11", "to_port": "GigabitEthernet0/1", "to_device_name": "ACC-SW-T1-2"},
    {"from_device": "10.100.1.3", "from_device_name": "DIST-SW02", "from_port": "GigabitEthernet1/0/1", "to_device": "10.100.20.10", "to_port": "GigabitEthernet0/1", "to_device_name": "ACC-SW-T2-1"},
    {"from_device": "10.100.1.3", "from_device_name": "DIST-SW02", "from_port": "GigabitEthernet1/0/2", "to_device": "10.100.20.11", "to_port": "GigabitEthernet0/1", "to_device_name": "ACC-SW-T2-2"}
]

MOCK_TOPOLOGY_CHANGES = [
    {
        "timestamp": "2026-06-02 15:10:43",
        "event_type": "link_down",
        "severity": "critical",
        "device_a": "10.100.1.2",
        "port_a": "GigabitEthernet1/0/1",
        "device_b": "10.100.10.10",
        "port_b": "GigabitEthernet0/1",
        "trigger_device": "10.100.10.10",
        "trigger_details": "A porta GigabitEthernet0/1 no dispositivo ACC-SW-T1-1 (10.100.10.10) foi detectada como DOWN (Cabo/SFP desconectado).",
        "description": "O link fisico entre DIST-SW01 (GigabitEthernet1/0/1) e ACC-SW-T1-1 (GigabitEthernet0/1) caiu."
    },
    {
        "timestamp": "2026-06-02 14:45:12",
        "event_type": "link_up",
        "severity": "info",
        "device_a": "10.100.1.1",
        "port_a": "GigabitEthernet1/0/24",
        "device_b": "10.11.3.1",
        "port_b": "eth0",
        "trigger_device": "Descoberta LLDP/CDP",
        "trigger_details": "Nova vizinhanca fisica estabelecida.",
        "description": "Nova conexao fisica estabelecida entre CORE-SW01 (GigabitEthernet1/0/24) e GW-BORDA01 (eth0)."
    }
]

@topology_bp.route('/api/topology')
def get_topology():
    nd = get_netdisco_client()
    if is_mock_mode() or not nd:
        nodes = []
        for dev in MOCK_DEVICES:
            nodes.append({
                "id": dev["ip"],
                "label": f"{dev['name']}\n({dev['ip']})",
                "title": f"Tipo: {dev['type']}",
                "group": dev["type"].lower().replace(" ", "_")
            })
            
        edges = []
        for i, link in enumerate(MOCK_LINKS):
            edges.append({
                "id": f"link_{i}",
                "from": link["from_device"],
                "to": link["to_device"],
                "label": f"{link['from_port']} ⇄ {link['to_port']}",
                "font": {"align": "horizontal"}
            })
        return jsonify({"nodes": nodes, "edges": edges})

    try:
        pt = PathTracer(nd)
        pt.build_topology_graph()
        
        nodes = []
        for node, data in pt.graph.nodes(data=True):
            dev_type = "Switch"
            if "gw" in data.get("name", "").lower() or "borda" in data.get("name", "").lower() or "router" in data.get("name", "").lower():
                dev_type = "Router L3"
            elif "core" in data.get("name", "").lower():
                dev_type = "Core Switch"
            elif "dist" in data.get("name", "").lower():
                dev_type = "Distribution Switch"
            else:
                dev_type = "Access Switch"

            nodes.append({
                "id": node,
                "label": f"{data.get('name', node)}\n({node})",
                "title": f"Tipo: {dev_type}",
                "group": dev_type.lower().replace(" ", "_")
            })

        edges = []
        idx = 0
        for u, v, data in pt.graph.edges(data=True):
            links = data.get("links", [])
            label_parts = []
            for l in links:
                label_parts.append(f"{l.get('from_port')}⇄{l.get('to_port')}")
            
            edges.append({
                "id": f"link_{idx}",
                "from": u,
                "to": v,
                "label": ", ".join(label_parts),
                "font": {"align": "horizontal"}
            })
            idx += 1

        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@topology_bp.route('/api/topology/changes')
def get_topology_changes():
    nd = get_netdisco_client()
    ln = get_librenms_client()
    if is_mock_mode() or not nd:
        return jsonify(MOCK_TOPOLOGY_CHANGES)
    try:
        tracker = TopologyTracker(nd, ln)
        return jsonify(tracker.check_topology_changes())
    except Exception as e:
        return jsonify({"error": str(e), "fallback_data": MOCK_TOPOLOGY_CHANGES}), 500

@topology_bp.route('/api/topology/stp-tc')
def get_stp_topology_triggers():
    ln = get_librenms_client()
    if is_mock_mode() or not ln:
        return jsonify([
            {
                "timestamp": "2026-06-02 16:24:52",
                "event_type": "stp_detected_tc_link",
                "severity": "warning",
                "device_a_ip": "172.16.11.51",
                "device_a_name": "sw crp2 5 33  almox g",
                "port_a": "GigabitEthernet1/0/24",
                "device_b_ip": "172.16.11.50",
                "device_b_name": "switch pabx 1",
                "port_b": "GigabitEthernet1/0/24",
                "description": "Detecao simultanea de MSTP Topology Change (DETECT TC) na porta GigabitEthernet1/0/24 de sw crp2 5 33  almox g (172.16.11.51) e porta GigabitEthernet1/0/24 de switch pabx 1 (172.16.11.50). Provavel link fisico entre eles."
            }
        ])
    try:
        hours = request.args.get('hours', default=24, type=int)
        tracker = StpTracker(ln)
        events = tracker.get_stp_topology_triggers(hours_back=hours)
        if not events and hours < 168:
            events = tracker.get_stp_topology_triggers(hours_back=168)
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@topology_bp.route('/api/trace-path')
def get_trace_path():
    src = request.args.get('src')
    dest = request.args.get('dest')

    if not src or not dest:
        return jsonify({"error": "Parametros 'src' e 'dest' sao obrigatorios."}), 400

    nd = get_netdisco_client()
    if is_mock_mode() or not nd:
        src_clean = src.strip().lower()
        dest_clean = dest.strip().lower()

        src_ip = None
        dest_ip = None
        for dev in MOCK_DEVICES:
            if src_clean == dev["ip"] or src_clean == dev["name"].lower():
                src_ip = dev["ip"]
            if dest_clean == dev["ip"] or dest_clean == dev["name"].lower():
                dest_ip = dev["ip"]

        if not src_ip or not dest_ip:
            return jsonify({"error": "Dispositivo de origem ou destino mock nao encontrado."}), 404

        if src_ip == dest_ip:
            return jsonify({
                "success": True,
                "same_device": True,
                "device": src_ip,
                "device_name": next(d["name"] for d in MOCK_DEVICES if d["ip"] == src_ip),
                "path": []
            })

        import collections
        adj = collections.defaultdict(list)
        for link in MOCK_LINKS:
            adj[link["from_device"]].append((link["to_device"], link["from_port"], link["to_port"]))
            adj[link["to_device"]].append((link["from_device"], link["to_port"], link["from_port"]))

        queue = collections.deque([[src_ip]])
        visited = {src_ip}
        path_nodes = None
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == dest_ip:
                path_nodes = path
                break
            for neighbor, _, _ in adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        if not path_nodes:
            return jsonify({"success": False, "error": "Nao ha caminho fisico mapeado."})

        path_details = []
        for i in range(len(path_nodes) - 1):
            curr = path_nodes[i]
            nxt = path_nodes[i+1]
            curr_links = []
            for neighbor, p_from, p_to in adj[curr]:
                if neighbor == nxt:
                    curr_links.append({"from_port": p_from, "to_port": p_to})

            curr_name = next(d["name"] for d in MOCK_DEVICES if d["ip"] == curr)
            nxt_name = next(d["name"] for d in MOCK_DEVICES if d["ip"] == nxt)

            path_details.append({
                "hop_index": i + 1,
                "from_device": curr,
                "from_device_name": curr_name,
                "to_device": nxt,
                "to_device_name": nxt_name,
                "links": curr_links
            })

        return jsonify({
            "success": True,
            "same_device": False,
            "source": src_ip,
            "source_name": next(d["name"] for d in MOCK_DEVICES if d["ip"] == src_ip),
            "destination": dest_ip,
            "destination_name": next(d["name"] for d in MOCK_DEVICES if d["ip"] == dest_ip),
            "hops_count": len(path_details),
            "path": path_details
        })

    try:
        pt = PathTracer(nd)
        pt.build_topology_graph()
        return jsonify(pt.trace_path(src, dest))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
