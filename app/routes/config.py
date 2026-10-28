from collections import defaultdict
from flask import Blueprint, jsonify, request
from app.services.config_service import ConfigService
from app.clients import is_mock_mode
from app.database.connection_pool import MySQLConnectionContext

config_bp = Blueprint('config', __name__)

@config_bp.route('/api/infrastructure/config', methods=['GET', 'POST'])
def handle_infrastructure_config():
    config = ConfigService.load_config()
    if request.method == 'GET':
        infra = config.get("monitored_infrastructure", {"switches": [], "wifi_bases": []})
        return jsonify(infra)
    elif request.method == 'POST':
        data = request.json or {}
        config["monitored_infrastructure"] = {
            "switches": data.get("switches", []),
            "wifi_bases": data.get("wifi_bases", [])
        }
        try:
            ConfigService.save_config(config)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@config_bp.route('/api/infrastructure/status')
def get_infrastructure_status():
    config = ConfigService.load_config()
    if is_mock_mode():
        return jsonify({
            "switches": [
                {
                    "ip": "10.11.0.248",
                    "name": "DC-DELL-ETH",
                    "uplinks": [
                        {
                            "port": "TenGigabitEthernet 1/10",
                            "alias": "Uplink SW 10.10.6.12 Cenario Virtual",
                            "dest_device": "SW 10.10.6.12 Cenario Virtual",
                            "dest_port": "Gi1/0/24",
                            "status": "up",
                            "admin_status": "up",
                            "speed": "1 Gbps",
                            "in_rate": "22.1 Kbps",
                            "out_rate": "20.8 Kbps"
                        }
                    ]
                }
            ],
            "wifi_bases": [
                {
                    "ip": "10.11.6.108",
                    "name": "Ruckus Almox",
                    "model": "R610",
                    "location": "Almoxarifado",
                    "source_switch": "corp_poe_almox-geral",
                    "source_port": "GigabitEthernet1/0/5",
                    "status": "online",
                    "latency": "2.4 ms",
                    "last_seen": "A alguns segundos"
                }
            ]
        })

    try:
        import pymysql
        db_cfg = config.get("databases", {}).get("librenms", {})
        infra = config.get("monitored_infrastructure", {"switches": [], "wifi_bases": []})
        switches_cfg = infra.get("switches", [])
        wifi_cfg = infra.get("wifi_bases", [])
        
        sw_groups = defaultdict(list)
        sw_names = {}
        for item in switches_cfg:
            ip = item.get("ip")
            if not ip:
                continue
            sw_names[ip] = item.get("name") or sw_names.get(ip) or ip
            
            if "port" in item:
                sw_groups[ip].append({
                    "port": item.get("port"),
                    "dest_device": item.get("dest_device") or "",
                    "dest_port": item.get("dest_port") or ""
                })
            elif "uplinks" in item:
                for up in item.get("uplinks", []):
                    if isinstance(up, dict):
                        sw_groups[ip].append({
                            "port": up.get("port"),
                            "dest_device": up.get("dest_device") or "",
                            "dest_port": up.get("dest_port") or ""
                        })
                    else:
                        sw_groups[ip].append({
                            "port": up,
                            "dest_device": "",
                            "dest_port": ""
                        })

        switches_status = []
        with MySQLConnectionContext("librenms_pool", db_cfg) as conn:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            
            for sw_ip, uplinks in sw_groups.items():
                sw_name = sw_names[sw_ip]
                uplinks_data = []
                for up in uplinks:
                    port_name = up.get("port")
                    if not port_name:
                        continue
                    uplinks_data.append({
                        "port": port_name,
                        "alias": up.get("dest_device") or "Sem descricao",
                        "dest_device": up.get("dest_device") or "",
                        "dest_port": up.get("dest_port") or "",
                        "status": "unknown",
                        "admin_status": "unknown",
                        "speed": "Desconhecido",
                        "in_rate": "0 bps",
                        "out_rate": "0 bps"
                    })
                
                ports_to_query = [up["port"] for up in uplinks if up.get("port")]
                if ports_to_query:
                    uplinks_tuple = tuple(ports_to_query)
                    # Safe check for tuple query (single item could cause syntax issues if not carefully parameterized)
                    cur.execute("""
                        SELECT p.ifName, p.ifDescr, p.ifAlias, p.ifOperStatus, p.ifAdminStatus, p.ifSpeed, p.ifInOctets_rate, p.ifOutOctets_rate
                        FROM ports p
                        JOIN devices d ON p.device_id = d.device_id
                        WHERE d.hostname = %s AND (p.ifName IN %s OR p.ifDescr IN %s);
                    """, (sw_ip, uplinks_tuple, uplinks_tuple))
                    
                    rows = cur.fetchall()
                    for r in rows:
                        db_port_name = r.get("ifName")
                        db_port_descr = r.get("ifDescr")
                        
                        speed_bps = r.get("ifSpeed") or 0
                        if speed_bps >= 10000000000:
                            speed_str = f"{speed_bps / 10000000000:.0f}0 Gbps"
                        elif speed_bps >= 1000000000:
                            speed_str = f"{speed_bps / 100000000:.0f} Gbps" if speed_bps == 1000000000 else f"{speed_bps / 1000000000:.1f} Gbps"
                        elif speed_bps >= 1000000:
                            speed_str = f"{speed_bps / 1000000:.0f} Mbps"
                        else:
                            speed_str = f"{speed_bps / 1000:.0f} Kbps" if speed_bps else "Desconhecido"
                            
                        in_bps = (r.get("ifInOctets_rate") or 0) * 8
                        out_bps = (r.get("ifOutOctets_rate") or 0) * 8
                        
                        def format_rate(rate_bps):
                            if rate_bps >= 1000000000:
                                return f"{rate_bps / 1000000000:.1f} Gbps"
                            elif rate_bps >= 1000000:
                                return f"{rate_bps / 1000000:.1f} Mbps"
                            elif rate_bps >= 1000:
                                return f"{rate_bps / 1000:.1f} Kbps"
                            else:
                                return f"{rate_bps} bps"
                                
                        for up_item in uplinks_data:
                            if up_item["port"] in (db_port_name, db_port_descr):
                                up_item["status"] = (r.get("ifOperStatus") or "unknown").lower()
                                up_item["admin_status"] = (r.get("ifAdminStatus") or "unknown").lower()
                                up_item["speed"] = speed_str
                                up_item["in_rate"] = format_rate(in_bps)
                                up_item["out_rate"] = format_rate(out_bps)
                                if r.get("ifAlias"):
                                    up_item["alias"] = r.get("ifAlias")
                
                switches_status.append({
                    "ip": sw_ip,
                    "name": sw_name,
                    "uplinks": uplinks_data
                })
                
            wifi_status = []
            for ap in wifi_cfg:
                ap_ip = ap.get("ip")
                ap_name = ap.get("name", ap_ip)
                ap_model = ap.get("model", "Desconhecido")
                ap_location = ap.get("location", "Nao informada")
                source_switch = ap.get("source_switch", "")
                source_port = ap.get("source_port", "")
                
                cur.execute("""
                    SELECT status, last_ping, last_ping_timetaken
                    FROM devices
                    WHERE hostname = %s OR sysName = %s;
                """, (ap_ip, ap_name))
                
                ap_row = cur.fetchone()
                if ap_row:
                    status_str = "online" if ap_row.get("status") == 1 else "offline"
                    lat_val = ap_row.get("last_ping_timetaken") or 0
                    lat_ms = f"{lat_val * 1000:.1f} ms" if lat_val < 5 else f"{lat_val:.1f} ms"
                    last_seen_val = ap_row.get("last_ping")
                    last_seen_str = str(last_seen_val).split(".")[0] if last_seen_val else "Nunca"
                else:
                    status_str = "offline"
                    lat_ms = "N/A"
                    last_seen_str = "Nao monitorado"
                    
                wifi_status.append({
                    "ip": ap_ip,
                    "name": ap_name,
                    "model": ap_model,
                    "location": ap_location,
                    "source_switch": source_switch,
                    "source_port": source_port,
                    "status": status_str,
                    "latency": lat_ms,
                    "last_seen": last_seen_str
                })
        
        return jsonify({
            "switches": switches_status,
            "wifi_bases": wifi_status
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
