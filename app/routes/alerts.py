import re
from datetime import datetime
from flask import Blueprint, jsonify
from app.services.config_service import ConfigService
from app.clients import is_mock_mode
from app.database.connection_pool import PostgresConnectionContext, MySQLConnectionContext
# Import loop-detector ping monitor
from app.analysis.ping_monitor import PingMonitor

alerts_bp = Blueprint('alerts', __name__)

# PingMonitor wrapper instance for routes
ping_monitor = PingMonitor(simulation_mode=is_mock_mode())

@alerts_bp.route('/api/alerts/intermittency')
def get_intermittency_alerts():
    try:
        # Use a lazy initialized ping monitor or similar if needed. For now, fetch latest data.
        return jsonify(ping_monitor.get_latest_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@alerts_bp.route('/api/alerts/loop-detector')
def get_loop_alerts():
    if is_mock_mode():
        return jsonify([
            {
                "mac": "e6:0a:17:94:07:99",
                "ip": "172.16.8.50",
                "switch_ip": "10.11.0.249",
                "switch_name": "DC-DELL-FIBRA",
                "interface": "TenGigabitEthernet 1/3 (Uplink SW 172.16.11.41)",
                "probable_origin": "172.16.11.41 (sw crp1_5.41 - redacao) / Porta GigabitEthernet1/0/29",
                "count": 728,
                "last_seen": "2026-06-19 11:30:00"
            }
        ])

    try:
        import pymysql
        config = ConfigService.load_config()
        db_cfg = config.get("databases", {}).get("librenms", {})

        rows = []
        # 1. Query LibreNMS syslog for flaps / loops
        with MySQLConnectionContext("librenms_pool", db_cfg) as conn:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute("""
                SELECT s.timestamp, d.hostname, d.sysName, s.msg 
                FROM syslog s
                JOIN devices d ON s.device_id = d.device_id
                WHERE s.timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                AND d.type = 'network'
                AND (
                    s.msg LIKE '%move%' 
                    OR s.msg LIKE '%flap%'
                    OR s.msg LIKE '%duplicate%'
                    OR s.msg LIKE '%flapping%'
                )
                ORDER BY s.timestamp DESC;
            """)
            rows = cur.fetchall()

        mac_stats = {}
        for r in rows:
            msg = r['msg']
            sw_ip = r['hostname']
            sw_name = r['sysName'] or 'N/A'
            ts = r['timestamp'].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r['timestamp'], datetime) else str(r['timestamp'])

            found_macs = [m.group(0) for m in re.finditer(r'([0-9a-fA-F]{2}[:]){5}[0-9a-fA-F]{2}|([0-9a-fA-F]{4}[.]){2}[0-9a-fA-F]{4}', msg)]
            if not found_macs:
                continue

            mac = found_macs[0].lower().replace('.', '').replace(':', '').replace('-', '')
            mac_formatted = ":".join([mac[i:i+2] for i in range(0, 12, 2)])

            port_name = "Detectada via Log"
            port_matches = re.findall(r'(?:TenGigabitEthernet|GigabitEthernet|Port-channel|ethernet|port)\s*[\d/]+', msg, re.IGNORECASE)
            if port_matches:
                port_name = " / ".join(set(port_matches))
            else:
                port_name = "Multiplas Portas (Loop)"

            key = (mac_formatted, sw_ip)
            if key not in mac_stats:
                mac_stats[key] = {
                    "mac": mac_formatted,
                    "switch_ip": sw_ip,
                    "switch_name": sw_name,
                    "interface": port_name,
                    "count": 0,
                    "last_seen": ts
                }
            mac_stats[key]["count"] += 1

        results = []
        # 2. Get IP address for each MAC from LibreNMS
        with MySQLConnectionContext("librenms_pool", db_cfg) as conn:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            for key, stats in mac_stats.items():
                mac_raw = stats["mac"].replace(':', '')
                cur.execute("SELECT ipv4_address FROM ipv4_mac WHERE mac_address = %s LIMIT 1;", (mac_raw,))
                ip_row = cur.fetchone()
                stats["ip"] = ip_row["ipv4_address"] if ip_row else "Desconhecido"
                results.append(stats)

        # 3. Resolve probable origin using Netdisco Postgres
        try:
            nd_cfg = config.get("databases", {}).get("netdisco", {})
            with PostgresConnectionContext("netdisco_pool", nd_cfg) as pg_conn:
                from psycopg2.extras import RealDictCursor
                pg_cur = pg_conn.cursor(cursor_factory=RealDictCursor)
                
                for stats in results:
                    mac_formatted = stats["mac"]
                    pg_cur.execute("""
                        SELECT n.switch::text, d.name as switch_name, n.port, n.vlan
                        FROM node n
                        JOIN device d ON n.switch = d.ip
                        WHERE n.mac = %s 
                        AND n.switch::text NOT IN ('10.11.0.248', '10.11.0.249', '172.16.11.248', '172.16.11.249')
                        ORDER BY n.time_recent DESC
                        LIMIT 1;
                    """, (mac_formatted,))
                    edge_row = pg_cur.fetchone()
                    if edge_row:
                        stats["probable_origin"] = f"{edge_row['switch'].split('/')[0]} ({edge_row['switch_name']}) / Porta {edge_row['port']}"
                    else:
                        stats["probable_origin"] = "Nao localizado na borda"
                pg_cur.close()
        except Exception as pg_ex:
            print(f"[Netdisco Query Error in loop-detector] {pg_ex}")
            for stats in results:
                stats["probable_origin"] = "Sem acesso a base de borda"

        results = sorted(results, key=lambda x: x["count"], reverse=True)
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
