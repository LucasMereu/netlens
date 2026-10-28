import re
from datetime import datetime, timedelta

class StpTracker:
    def __init__(self, librenms_client):
        self.librenms = librenms_client

    def get_stp_topology_triggers(self, hours_back=2):
        if not self.librenms:
            return []

        # Calcula o timestamp de início (padrão 2 horas para evitar sobrecarga de logs densos)
        start_time = (datetime.now() - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        all_logs = []
        current_from = start_time
        pages = 0
        max_pages = 15 # Limite para evitar lentidão ou loop infinito

        while pages < max_pages:
            pages += 1
            try:
                # Query syslog logs from LibreNMS
                result = self.librenms._request("logs/syslog", params={"from": current_from, "limit": 1000})
                logs = result.get("logs", [])
                if not logs:
                    break
                all_logs.extend(logs)
                if len(logs) < 1000:
                    break
                
                # O último log define o ponto de partida da próxima página
                last_timestamp = logs[-1]['timestamp']
                if last_timestamp == current_from:
                    break
                current_from = last_timestamp
            except Exception as e:
                print(f"[STP TRACKER ERROR] Falha ao consultar logs do LibreNMS na página {pages}: {e}")
                break

        # Compilar expressões regulares para transição física de interfaces
        regex_h3c = re.compile(r"([a-zA-Z0-9/\-]+)\s+link\s+status\s+is\s+(UP|DOWN)", re.IGNORECASE)
        regex_online = re.compile(r"port\s+([a-zA-Z0-9/\-]+)\s+is\s+now\s+(on-line|off-line|online|offline)", re.IGNORECASE)
        regex_link = re.compile(r"LINK\s+-\s+(Up|Down)", re.IGNORECASE)

        raw_detected_events = []
        notified_events = []
        link_events = []

        for l in all_logs:
            msg = l.get("msg", "")
            timestamp = l.get("timestamp")
            hostname = l.get("hostname")
            sysname = l.get("sysName") or hostname or "Desconhecido"

            # 1. Detecções locais de Topology Change (ex: %%10MSTP/6/MSTP_DETECTED_TC)
            if "MSTP_DETECTED_TC" in msg or "detected a topology change" in msg:
                port_match = re.search(r"port\s+([a-zA-Z0-9/\-]+)", msg)
                port = port_match.group(1) if port_match else "Indeterminada"
                raw_detected_events.append({
                    "timestamp": timestamp,
                    "device_ip": hostname,
                    "device_name": sysname,
                    "port": port,
                    "msg": msg
                })
                continue

            # 2. Notificações propagadas de STP (ex: %%10MSTP/6/MSTP_NOTIFIED_TC)
            if "MSTP_NOTIFIED_TC" in msg or "Topology Change Received" in msg or "was notified of a topology change" in msg:
                port_match = re.search(r"port\s+([a-zA-Z0-9/\-]+)", msg)
                port = port_match.group(1) if port_match else "Indeterminada"
                notified_events.append({
                    "timestamp": timestamp,
                    "device_ip": hostname,
                    "device_name": sysname,
                    "port": port,
                    "msg": msg
                })
                continue

            # 3. Transições físicas de links
            m = regex_h3c.search(msg)
            if m:
                link_events.append({
                    "timestamp": timestamp,
                    "device_ip": hostname,
                    "device_name": sysname,
                    "port": m.group(1),
                    "status": m.group(2).upper()
                })
                continue
            m = regex_online.search(msg)
            if m:
                status = "UP" if "on" in m.group(2).lower() else "DOWN"
                link_events.append({
                    "timestamp": timestamp,
                    "device_ip": hostname,
                    "device_name": sysname,
                    "port": m.group(1),
                    "status": status
                })
                continue
            m = regex_link.search(msg)
            if m:
                status = m.group(1).upper()
                port_m = re.search(r",\s*(\d+)$", msg)
                port = port_m.group(1) if port_m else "Indeterminada"
                link_events.append({
                    "timestamp": timestamp,
                    "device_ip": hostname,
                    "device_name": sysname,
                    "port": port,
                    "status": status
                })
                continue

        correlated_events = []

        # -- ALGORITMO A: Correlacionar DETECTED_TC das extremidades do link --
        used_indices = set()
        raw_detected_events.sort(key=lambda x: x["timestamp"], reverse=True)
        for i, ev_a in enumerate(raw_detected_events):
            if i in used_indices:
                continue
            dt_a = datetime.strptime(ev_a["timestamp"], "%Y-%m-%d %H:%M:%S")
            paired_event = None
            for j in range(i + 1, len(raw_detected_events)):
                if j in used_indices:
                    continue
                ev_b = raw_detected_events[j]
                dt_b = datetime.strptime(ev_b["timestamp"], "%Y-%m-%d %H:%M:%S")
                if abs((dt_a - dt_b).total_seconds()) <= 5 and ev_a["device_ip"] != ev_b["device_ip"]:
                    paired_event = ev_b
                    used_indices.add(j)
                    break
            if paired_event:
                correlated_events.append({
                    "timestamp": ev_a["timestamp"],
                    "event_type": "stp_detected_tc_link",
                    "severity": "warning",
                    "device_a_ip": ev_a["device_ip"] if ev_a["device_ip"] else "N/A",
                    "device_a_name": ev_a["device_name"],
                    "port_a": ev_a["port"],
                    "device_b_ip": paired_event["device_ip"] if paired_event["device_ip"] else "N/A",
                    "device_b_name": paired_event["device_name"],
                    "port_b": paired_event["port"],
                    "description": (
                        f"Detecção simultânea de MSTP Topology Change (DETECT TC) na porta {ev_a['port']} de "
                        f"{ev_a['device_name']} e porta {paired_event['port']} de "
                        f"{paired_event['device_name']}. Provável link físico direto entre eles."
                    )
                })
            else:
                correlated_events.append({
                    "timestamp": ev_a["timestamp"],
                    "event_type": "stp_detected_tc_single",
                    "severity": "info",
                    "device_a_ip": ev_a["device_ip"] if ev_a["device_ip"] else "N/A",
                    "device_a_name": ev_a["device_name"],
                    "port_a": ev_a["port"],
                    "device_b_ip": None,
                    "device_b_name": None,
                    "port_b": None,
                    "description": (
                        f"O switch {ev_a['device_name']} detectou uma mudança de topologia local "
                        f"(MSTP DETECT TC) na porta {ev_a['port']}."
                    )
                })

        # -- ALGORITMO B: Correlacionar NOTIFIED_TC com alterações físicas de portas --
        notified_groups = []
        notified_events.sort(key=lambda x: x["timestamp"])
        for ev in notified_events:
            dt_ev = datetime.strptime(ev["timestamp"], "%Y-%m-%d %H:%M:%S")
            added = False
            for grp in notified_groups:
                dt_grp = datetime.strptime(grp["timestamp"], "%Y-%m-%d %H:%M:%S")
                if abs((dt_ev - dt_grp).total_seconds()) <= 5:
                    grp["devices"].append(ev["device_name"])
                    grp["events_count"] += 1
                    added = True
                    break
            if not added:
                notified_groups.append({
                    "timestamp": ev["timestamp"],
                    "devices": [ev["device_name"]],
                    "events_count": 1
                })

        for grp in notified_groups:
            dt_tcn = datetime.strptime(grp["timestamp"], "%Y-%m-%d %H:%M:%S")
            possible_triggers = []
            
            # Buscar transições que ocorreram até 3 min antes do TCN (ou até 10s depois por delay)
            for le in link_events:
                dt_le = datetime.strptime(le["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff = (dt_tcn - dt_le).total_seconds()
                if -10 <= diff <= 180:
                    possible_triggers.append(le)
            
            # Deduplicar as transições de link mantendo a ordem cronológica
            unique_triggers = []
            seen = set()
            for pt in reversed(possible_triggers):
                tkey = (pt["device_ip"], pt["port"], pt["status"])
                if tkey not in seen:
                    seen.add(tkey)
                    unique_triggers.append(pt)
            unique_triggers.reverse()

            if unique_triggers:
                trigger_descriptions = []
                for ut in unique_triggers:
                    trigger_descriptions.append(f"{ut['device_name']} ({ut['device_ip']}) porta {ut['port']} ({ut['status']})")
                
                desc = (
                    f"Mudança de topologia propagada (NOTIFIED TC) recebida por {grp['events_count']} switches. "
                    f"Prováveis disparadores físicos detectados nos 3 min anteriores: "
                    f"{', '.join(trigger_descriptions)}."
                )
                
                correlated_events.append({
                    "timestamp": grp["timestamp"],
                    "event_type": "stp_notified_tc_group",
                    "severity": "warning",
                    "device_a_ip": unique_triggers[0]["device_ip"] if unique_triggers[0]["device_ip"] else "N/A",
                    "device_a_name": unique_triggers[0]["device_name"] if unique_triggers[0]["device_name"] else "Desconhecido",
                    "port_a": unique_triggers[0]["port"],
                    "device_b_ip": None,
                    "device_b_name": None,
                    "port_b": None,
                    "description": desc
                })
            else:
                desc = f"Mudança de topologia propagada (NOTIFIED TC) recebida por {grp['events_count']} switches na rede. Nenhuma transição física recente no syslog."
                correlated_events.append({
                    "timestamp": grp["timestamp"],
                    "event_type": "stp_notified_tc_group",
                    "severity": "info",
                    "device_a_ip": "N/A",
                    "device_a_name": "Propagação MSTP",
                    "port_a": "N/A",
                    "device_b_ip": None,
                    "device_b_name": None,
                    "port_b": None,
                    "description": desc
                })

        # Correlacionar autores para cada evento
        for ev in correlated_events:
            # Check device A
            author_a, method_a, details_a = self._find_probable_author(ev.get("device_a_ip"), ev["timestamp"], all_logs)
            # Check device B (if any)
            author_b, method_b, details_b = self._find_probable_author(ev.get("device_b_ip"), ev["timestamp"], all_logs)
            
            if author_a:
                ev["probable_author"] = author_a
                ev["author_method"] = method_a
                ev["author_details"] = details_a
            elif author_b:
                ev["probable_author"] = author_b
                ev["author_method"] = method_b
                ev["author_details"] = details_b
            else:
                ev["probable_author"] = "Desconhecido / Sistema"
                ev["author_method"] = "N/A"
                ev["author_details"] = "Nenhuma atividade administrativa recente detectada no syslog"

        # Ordenar os eventos finais pelos mais recentes
        correlated_events.sort(key=lambda x: x["timestamp"], reverse=True)
        return correlated_events

    def _find_probable_author(self, device_ip, event_time_str, all_logs):
        if not device_ip or device_ip == "N/A":
            return None, None, None
            
        try:
            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None, None, None
            
        # Analisa a janela de 15 minutos anteriores até 1 minuto depois
        start_win = event_time - timedelta(minutes=15)
        end_win = event_time + timedelta(minutes=1)
        
        # Expressões regulares para capturar autores e detalhes
        pat_cli = re.compile(r"%CLI-6-([a-zA-Z0-9\s\-_\/]+)\s+by\s+([a-zA-Z0-9\.\-_]+)", re.IGNORECASE)
        pat_web = re.compile(r"WEBOPT_.*by\s+([a-zA-Z0-9\.\-_]+)", re.IGNORECASE)
        pat_login = re.compile(r"User\s+([a-zA-Z0-9\.\-_]+)\s+(?:logged\s+in|from|via)", re.IGNORECASE)
        pat_by = re.compile(r"by\s+([a-zA-Z0-9\.\-_]+)", re.IGNORECASE)
        
        candidates = []
        
        for l in all_logs:
            msg = l.get("msg", "")
            ts_str = l.get("timestamp")
            hostname = l.get("hostname")
            
            if hostname != device_ip:
                continue
                
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
                
            if start_win <= ts <= end_win:
                author = None
                method = "CLI"
                details = msg
                
                m_cli = pat_cli.search(msg)
                if m_cli:
                    author = m_cli.group(2)
                    details = f"Comando: {m_cli.group(1).strip()}"
                    method = "CLI/Console"
                else:
                    m_web = pat_web.search(msg)
                    if m_web:
                        author = m_web.group(1)
                        details = msg
                        method = "Web"
                    else:
                        m_login = pat_login.search(msg)
                        if m_login:
                            author = m_login.group(1)
                            method = "Login"
                            if "HTTPS" in msg or "web" in msg:
                                method = "Web/HTTPS"
                            elif "vty" in msg or "ssh" in msg:
                                method = "SSH"
                        else:
                            m_by = pat_by.search(msg)
                            if m_by:
                                author = m_by.group(1)
                                if "web" in msg:
                                    method = "Web"
                                
                if author:
                    if author.lower() in ["tacmon"]:
                        continue
                    candidates.append((ts, author, method, details))
                    
        if candidates:
            # Ordena pelo mais próximo do evento
            candidates.sort(key=lambda x: x[0], reverse=True)
            closest = candidates[0]
            return closest[1], closest[2], closest[3]
            
        return None, None, None

