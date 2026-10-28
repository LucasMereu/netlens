import re
from datetime import datetime, timedelta

def normalize_port_name(name):
    if not name:
        return ""
    name = str(name).lower().strip()
    name = re.sub(r"^(port|interface|eth)\s*", "", name)
    name = name.replace(" ", "").replace("ethernet", "")
    name = name.replace("gigabit", "gi").replace("tengigabit", "te").replace("fast", "fa")
    return name

class PortEventTracker:
    def __init__(self, librenms_client, netdisco_client=None):
        self.librenms = librenms_client
        self.netdisco = netdisco_client

    @staticmethod
    def classify_flapping(flaps, warn_threshold=3, crit_threshold=6):
        """Classifica o nível de severidade de flapping com base nos limiares."""
        try:
            flaps = int(flaps)
            warn_threshold = int(warn_threshold)
            crit_threshold = int(crit_threshold)
        except (ValueError, TypeError):
            return "none"
        if flaps >= crit_threshold:
            return "critical"
        elif flaps >= warn_threshold:
            return "warning"
        return "none"

    _classify_flapping = classify_flapping

    def _fetch_flaps_and_stp(self, hours_back=24, settings=None):
        """
        Consulta o banco de dados do LibreNMS para coletar:
        1. Transições de estado (UP/DOWN) no eventlog por port_id nas últimas X horas.
        2. Portas com status 'blocking' na tabela ports_stp.
        3. Eventos de bloqueio por STP e BPDU Protect no syslog correspondentes aos padrões configurados.
        """
        flaps_by_port_id = {}
        flaps_by_dev_port = {}
        stp_by_dev_port = {}
        stp_blocked_port_ids = set()

        if not self.librenms:
            return flaps_by_port_id, flaps_by_dev_port, stp_by_dev_port, stp_blocked_port_ids

        patterns = (settings or {}).get("stp_patterns", [
            "Blocked by STP", "BPDU Protection", "BPDU", "MSTP_BLOCKED",
            "MSTP_DISCARDING", "BLOCK_BPDUGUARD", "loop-protect", "err-disable"
        ])

        conn = None
        if hasattr(self.librenms, 'get_db_connection'):
            try:
                conn = self.librenms.get_db_connection()
            except Exception as e:
                print(f"[PORT EVENTS] Falha ao obter conexão MySQL do LibreNMS: {e}")

        if conn:
            try:
                with conn.cursor() as cur:
                    h_int = int(hours_back)
                    # 1. Contagem de flapping no eventlog
                    try:
                        cur.execute(f"""
                            SELECT reference, COUNT(*) as flaps, MAX(datetime) as last_flap
                            FROM eventlog
                            WHERE type = 'interface' 
                              AND (message LIKE '%up -> down%' OR message LIKE '%down -> up%')
                              AND datetime >= NOW() - INTERVAL {h_int} HOUR
                            GROUP BY reference
                        """)
                        for r in cur.fetchall():
                            pid = str(r[0])
                            flaps_by_port_id[pid] = int(r[1])
                    except Exception as ex_ev:
                        print(f"[PORT EVENTS] Erro ao consultar eventlog: {ex_ev}")

                    # 2. Portas bloqueadas em ports_stp
                    try:
                        cur.execute("SELECT port_id, state FROM ports_stp WHERE state = 'blocking'")
                        for r in cur.fetchall():
                            stp_blocked_port_ids.add(int(r[0]))
                    except Exception:
                        pass

                    # 3. Bloqueios de STP e BPDU no syslog
                    if patterns:
                        try:
                            like_clauses = " OR ".join(["s.msg LIKE %s" for _ in patterns])
                            like_params = [f"%{p}%" for p in patterns]
                            query = f"""
                                SELECT s.device_id, s.timestamp, s.msg, s.program
                                FROM syslog s
                                WHERE ({like_clauses})
                                  AND s.timestamp >= NOW() - INTERVAL {h_int} HOUR
                                ORDER BY s.timestamp DESC
                                LIMIT 2000
                            """
                            cur.execute(query, like_params)
                            for r in cur.fetchall():
                                dev_id = r[0]
                                ts = str(r[1])
                                msg = r[2]
                                prog = r[3] or ""

                                # Extrair identificador de porta da mensagem de log
                                m = (
                                    re.search(r"port\s+([a-zA-Z0-9/\-]+)", msg, re.IGNORECASE) or
                                    re.search(r"interface\s+([a-zA-Z0-9/\-]+)", msg, re.IGNORECASE) or
                                    re.search(r"Instance\s+\d+.*?port\s+([a-zA-Z0-9/\-]+)", msg, re.IGNORECASE)
                                )
                                if m:
                                    raw_p = m.group(1)
                                    norm_p = normalize_port_name(raw_p)
                                    key = (dev_id, norm_p)
                                    if key not in stp_by_dev_port:
                                        stp_by_dev_port[key] = {
                                            "timestamp": ts,
                                            "message": msg,
                                            "program": prog,
                                            "raw_port": raw_p,
                                            "type": "BPDU Protect / STP Block"
                                        }
                                    flaps_by_dev_port[key] = flaps_by_dev_port.get(key, 0) + 1
                        except Exception as ex_sl:
                            print(f"[PORT EVENTS] Erro ao consultar syslog STP: {ex_sl}")

            except Exception as ex:
                print(f"[PORT EVENTS] Erro geral ao consultar DB LibreNMS: {ex}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        return flaps_by_port_id, flaps_by_dev_port, stp_by_dev_port, stp_blocked_port_ids

    def get_recent_port_events(self, limit=100, hours_back=None, min_flaps=None, stp_only=False):
        if not self.librenms:
            return []

        try:
            # Carrega configurações dinâmicas de eventos de portas
            settings = {
                "flapping_warning_threshold": 3,
                "flapping_critical_threshold": 6,
                "default_window_hours": 24,
                "stp_patterns": [
                    "Blocked by STP", "BPDU Protection", "BPDU", "MSTP_BLOCKED",
                    "MSTP_DISCARDING", "BLOCK_BPDUGUARD", "loop-protect", "err-disable"
                ]
            }
            try:
                from app.services.config_service import ConfigService
                cfg = ConfigService.load_config()
                if "port_events_settings" in cfg:
                    settings.update(cfg["port_events_settings"])
            except Exception:
                pass

            win_hours = hours_back if (hours_back and hours_back > 0) else settings.get("default_window_hours", 24)
            warn_threshold = settings.get("flapping_warning_threshold", 3)
            crit_threshold = settings.get("flapping_critical_threshold", 6)

            # 0. Coleta a topologia física para cruzar dados de vizinhança
            topo_map = {}
            if self.netdisco:
                try:
                    topology_links = self.netdisco.get_topology() or []
                    for link in topology_links:
                        dev_a = link.get("from_device")
                        port_a = normalize_port_name(link.get("from_port"))
                        dev_b = link.get("to_device")
                        port_b = normalize_port_name(link.get("to_port"))
                        
                        name_a = link.get("from_device_name") or dev_a
                        name_b = link.get("to_device_name") or dev_b
                        
                        if dev_a and port_a:
                            topo_map[(dev_a, port_a)] = {
                                "neighbor_ip": dev_b,
                                "neighbor_name": name_b,
                                "neighbor_port": link.get("to_port")
                            }
                        if dev_b and port_b:
                            topo_map[(dev_b, port_b)] = {
                                "neighbor_ip": dev_a,
                                "neighbor_name": name_a,
                                "neighbor_port": link.get("from_port")
                            }
                except Exception as ex:
                    print(f"[PORT EVENTS] Erro ao carregar topologia: {ex}")

            # 1. Busca dispositivos e mapeia uptime e data do último poll
            devices = self.librenms.get_devices()
            device_uptime = {}
            device_names = {}
            device_poll_time = {}
            device_ips = {}

            for d in devices:
                d_id = d.get("device_id")
                if d_id:
                    device_uptime[d_id] = float(d.get("uptime") or 0)
                    device_names[d_id] = d.get("sysName") or d.get("hostname") or f"Device {d_id}"
                    device_ips[d_id] = d.get("hostname", "N/A")
                    
                    poll_str = d.get("last_polled")
                    if poll_str:
                        try:
                            device_poll_time[d_id] = datetime.strptime(poll_str, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            device_poll_time[d_id] = datetime.now()
                    else:
                        device_poll_time[d_id] = datetime.now()

            # 2. Coleta dados de flapping e bloqueios STP na janela selecionada
            flaps_by_pid, flaps_by_dev_port, stp_by_dev_port, stp_blocked_pids = self._fetch_flaps_and_stp(win_hours, settings)

            # 3. Busca todas as portas do LibreNMS com colunas necessárias
            valid_cols = "port_id,device_id,ifName,ifOperStatus,ifLastChange"
            ports = self.librenms._request("ports", params={"columns": valid_cols}).get("ports", [])

            port_events = []
            for p in ports:
                d_id = p.get("device_id")
                if d_id not in device_uptime:
                    continue
                    
                last_change = p.get("ifLastChange")
                if not last_change:
                    continue
                    
                try:
                    change_ticks = float(last_change)
                    change_seconds = change_ticks / 100.0
                    dev_seconds = device_uptime[d_id]
                    
                    if change_seconds > 0 and dev_seconds >= change_seconds:
                        seconds_ago = dev_seconds - change_seconds
                        
                        # Limita o histórico a 365 dias para evitar anomalias de contador SNMP
                        if seconds_ago < 365 * 24 * 3600:
                            poll_dt = device_poll_time[d_id]
                            change_dt = poll_dt - timedelta(seconds=seconds_ago)
                            
                            # Calcula tempo relativo
                            total_seconds = int((datetime.now() - change_dt).total_seconds())
                            if total_seconds < 0:
                                relative_time = "há poucos segundos"
                            elif total_seconds >= 86400:
                                days = total_seconds // 86400
                                relative_time = f"há {days} dia" if days == 1 else f"há {days} dias"
                            elif total_seconds >= 3600:
                                hours = total_seconds // 3600
                                relative_time = f"há {hours} hora" if hours == 1 else f"há {hours} horas"
                            elif total_seconds >= 60:
                                minutes = total_seconds // 60
                                relative_time = f"há {minutes} minuto" if minutes == 1 else f"há {minutes} minutos"
                            else:
                                relative_time = "há poucos segundos"

                            port_name = p.get("ifName") or ""
                            norm_port = normalize_port_name(port_name)
                            dev_ip = device_ips[d_id]
                            
                            # Cruza com a topologia para achar o switch vizinho
                            neighbor = topo_map.get((dev_ip, norm_port))
                            if not neighbor:
                                dev_name = device_names[d_id]
                                neighbor = topo_map.get((dev_name, norm_port))
                                
                            neighbor_info = None
                            if neighbor:
                                neighbor_info = {
                                    "neighbor_name": neighbor["neighbor_name"],
                                    "neighbor_ip": neighbor["neighbor_ip"],
                                    "neighbor_port": neighbor["neighbor_port"]
                                }

                            # 4. Cruzamento de Flapping & STP
                            pid_int = p.get("port_id")
                            pid_str = str(pid_int)
                            flaps = flaps_by_pid.get(pid_str, 0)
                            dev_port_key = (d_id, norm_port)
                            dev_port_flaps = flaps_by_dev_port.get(dev_port_key, 0)
                            total_flaps = max(flaps, dev_port_flaps)

                            is_flapping = total_flaps >= warn_threshold
                            flap_severity = PortEventTracker.classify_flapping(total_flaps, warn_threshold, crit_threshold)

                            # Detecção de Bloqueio STP / BPDU Protect
                            is_stp_blocked = False
                            stp_details = None

                            if pid_int in stp_blocked_pids:
                                is_stp_blocked = True
                                stp_details = {
                                    "timestamp": change_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                    "message": "Porta em estado de bloqueio (STP blocking)",
                                    "type": "STP Blocking"
                                }

                            if dev_port_key in stp_by_dev_port:
                                is_stp_blocked = True
                                stp_details = stp_by_dev_port[dev_port_key]
                            elif (d_id, str(port_name).strip().lower()) in stp_by_dev_port:
                                is_stp_blocked = True
                                stp_details = stp_by_dev_port[(d_id, str(port_name).strip().lower())]

                            # Filtros opcionais
                            if stp_only and not is_stp_blocked:
                                continue
                            if min_flaps and total_flaps < min_flaps:
                                continue

                            port_events.append({
                                "port_id": pid_int,
                                "device_id": d_id,
                                "device_name": device_names[d_id],
                                "device_ip": dev_ip,
                                "port_name": port_name,
                                "status": p.get("ifOperStatus"),
                                "timestamp": change_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "relative_time": relative_time,
                                "neighbor": neighbor_info,
                                "flaps": total_flaps,
                                "is_flapping": is_flapping,
                                "flap_severity": flap_severity,
                                "stp_blocked": is_stp_blocked,
                                "stp_details": stp_details,
                                "dt": change_dt
                            })
                except Exception:
                    pass

            # Ordena pelos eventos mais recentes
            port_events.sort(key=lambda x: x["dt"], reverse=True)
            
            # Remove o objeto datetime temporário antes de retornar
            for pe in port_events:
                pe.pop("dt", None)

            return port_events[:limit]
        except Exception as e:
            print(f"[PORT EVENTS ERROR] Erro ao calcular eventos de portas: {e}")
            return []
