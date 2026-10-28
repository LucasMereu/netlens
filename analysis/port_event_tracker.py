from datetime import datetime, timedelta

def normalize_port_name(name):
    if not name:
        return ""
    name = str(name).lower().replace(" ", "").replace("ethernet", "")
    name = name.replace("gigabit", "gi").replace("tengigabit", "te").replace("fast", "fa")
    return name

class PortEventTracker:
    def __init__(self, librenms_client, netdisco_client=None):
        self.librenms = librenms_client
        self.netdisco = netdisco_client

    def get_recent_port_events(self, limit=100):
        if not self.librenms:
            return []

        try:
            # 0. Coleta a topologia física para cruzar dados
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

            # 2. Busca todas as portas do LibreNMS com colunas necessárias
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


                            # Cruza com a topologia para achar o switch vizinho
                            port_name = p.get("ifName")
                            norm_port = normalize_port_name(port_name)
                            dev_ip = device_ips[d_id]
                            
                            neighbor = topo_map.get((dev_ip, norm_port))
                            if not neighbor:
                                # Tenta buscar pelo sysName do dispositivo caso o IP divirja
                                dev_name = device_names[d_id]
                                neighbor = topo_map.get((dev_name, norm_port))
                                
                            neighbor_info = None
                            if neighbor:
                                neighbor_info = {
                                    "neighbor_name": neighbor["neighbor_name"],
                                    "neighbor_ip": neighbor["neighbor_ip"],
                                    "neighbor_port": neighbor["neighbor_port"]
                                }

                            port_events.append({
                                "port_id": p.get("port_id"),
                                "device_id": d_id,
                                "device_name": device_names[d_id],
                                "device_ip": device_ips[d_id],
                                "port_name": port_name,
                                "status": p.get("ifOperStatus"),
                                "timestamp": change_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "relative_time": relative_time,
                                "neighbor": neighbor_info,
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
