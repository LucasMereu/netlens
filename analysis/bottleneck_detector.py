class BottleneckDetector:
    def __init__(self, librenms_client=None, zabbix_client=None):
        self.librenms = librenms_client
        self.zabbix = zabbix_client

    def detect_bottlenecks(self, util_threshold=80.0):
        """Busca gargalos de tráfego, erros físicos e descartes de buffer."""
        bottlenecks = []
        
        # O LibreNMS é ideal para isso pois monitora todas as portas via SNMP de forma granular
        if self.librenms:
            try:
                # Busca dispositivos para mapear ID -> IP/Hostname
                devices = self.librenms.get_devices()
                device_map = {}
                device_names = {}
                for d in devices:
                    d_id = d.get("device_id")
                    if d_id:
                        device_map[d_id] = d.get("hostname", "N/A")
                        device_names[d_id] = d.get("sysName") or d.get("hostname") or f"Device {d_id}"

                # 1. Busca portas com alta utilização de banda
                high_util_ports = self.librenms.get_high_utilization_ports(threshold_pct=util_threshold)
                for port in high_util_ports:
                    d_id = port.get("device_id")
                    bottlenecks.append({
                        "type": "high_utilization",
                        "severity": "critical" if port["util_pct"] >= 95.0 else "warning",
                        "device_id": d_id,
                        "device_name": device_names.get(d_id, f"Device {d_id}"),
                        "device_ip": device_map.get(d_id, "N/A"),
                        "port_name": port.get("ifName") or port.get("ifDescr"),
                        "port_alias": port.get("ifAlias"),
                        "speed_mbps": port["speed_mbps"],
                        "util_pct": port["util_pct"],
                        "details": f"Porta operando a {port['util_pct']}% da capacidade total ({port['speed_mbps']} Mbps). Entrada: {port['in_rate_mbps']} Mbps, Saída: {port['out_rate_mbps']} Mbps."
                    })

                # 2. Busca portas com taxas de erro ou descarte
                error_ports = self.librenms.get_error_ports()
                for port in error_ports:
                    d_id = port.get("device_id")
                    in_err = int(port.get("ifInErrors") or 0)
                    out_err = int(port.get("ifOutErrors") or 0)
                    in_disc = int(port.get("ifInDiscards") or 0)
                    out_disc = int(port.get("ifOutDiscards") or 0)

                    speed = float(port.get("ifSpeed") or 0)
                    speed_mbps = round(speed / 1000000.0, 2) if speed else "N/A"

                    # Severity baseada na criticidade
                    if in_err > 100 or out_err > 100:
                        severity = "high"
                    elif in_disc > 1000 or out_disc > 1000:
                        severity = "warning"
                    else:
                        severity = "info"

                    details_list = []
                    if in_err > 0 or out_err > 0:
                        details_list.append(f"Erros de pacote: Entrada={in_err}, Saída={out_err}")
                    if in_disc > 0 or out_disc > 0:
                        details_list.append(f"Descartes de Buffer (Queue drops): Entrada={in_disc}, Saída={out_disc}")

                    bottlenecks.append({
                        "type": "port_errors_discards",
                        "severity": severity,
                        "device_id": d_id,
                        "device_name": device_names.get(d_id, f"Device {d_id}"),
                        "device_ip": device_map.get(d_id, "N/A"),
                        "port_name": port.get("ifName") or port.get("ifDescr"),
                        "port_alias": port.get("ifAlias"),
                        "speed_mbps": speed_mbps,
                        "details": " | ".join(details_list) + f" (Sinaliza possíveis problemas físicos ou saturação de buffers)."
                    })

            except Exception as e:
                # Se falhar o LibreNMS, vamos reportar ou tentar o Zabbix
                pass

        # Se tivermos o Zabbix e o LibreNMS falhou (ou como complemento)
        if not bottlenecks and self.zabbix:
            try:
                # Busca alertas ativos no Zabbix que mencionem links, erros ou utilização
                alerts = self.zabbix.get_active_alerts()
                for alert in alerts:
                    desc = alert.get("description", "").lower()
                    if any(x in desc for x in ["traffic", "utilization", "bandwidth", "high link", "error", "discard", "lost", "packet"]):
                        severity_map = {
                            "1": "info",
                            "2": "warning",
                            "3": "warning",
                            "4": "high",
                            "5": "critical"
                        }
                        priority = str(alert.get("priority", "1"))
                        
                        hosts = alert.get("hosts", [])
                        host_name = hosts[0].get("name") if hosts else "Desconhecido"

                        bottlenecks.append({
                            "type": "zabbix_trigger_alert",
                            "severity": severity_map.get(priority, "warning"),
                            "device_name": host_name,
                            "device_ip": "N/A",
                            "port_name": "Ver Zabbix",
                            "details": f"Alerta ativo no Zabbix: {alert.get('description')}"
                        })
            except Exception:
                pass

        return bottlenecks
