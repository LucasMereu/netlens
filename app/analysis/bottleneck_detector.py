"""
Módulo de detecção de gargalos de tráfego (saturação de banda) e
erros físicos / descartes de buffer em interfaces de rede.
Fonte de dados: LibreNMS (SNMP Polling em tempo real) com fallback para Zabbix.
"""
import re
from app.services.config_service import ConfigService

class BottleneckDetector:
    def __init__(self, librenms_client=None, zabbix_client=None):
        self.librenms = librenms_client
        self.zabbix = zabbix_client

    @staticmethod
    def is_virtual_interface(if_name, if_type=None):
        """Verifica se a interface é puramente lógica/virtual."""
        name_lower = str(if_name or "").lower().strip()
        type_lower = str(if_type or "").lower().strip()

        # Tipos conhecidos do SNMP MIB
        virtual_types = {
            'softwareloopback', 'l3ipvlan', 'l2vlan', 'tunnel',
            'other', 'propvirtual', 'bridge', 'loopback'
        }
        if type_lower in virtual_types:
            return True

        # Padrões comuns de nomes virtuais
        virtual_patterns = [
            r'^lo\d*$', r'^loopback\d*$', r'^null\d*$', r'^sit\d*$',
            r'^tun\d*$', r'^veth[a-f0-9]+$', r'^docker\d*$', r'^br\d*$',
            r'^vlan\s*\d+$', r'^vlan\d+$'
        ]
        for pat in virtual_patterns:
            if re.match(pat, name_lower):
                return True

        return False

    def _get_device_maps(self, force_refresh=False):
        """Retorna mapas de ID -> IP, ID -> Nome e ID -> Metadados (is_switch, os, hardware)."""
        device_map = {}
        device_names = {}
        device_meta = {}
        if not self.librenms:
            return device_map, device_names, device_meta
        try:
            devices = self.librenms.get_devices(force_refresh=force_refresh)
            switch_os = {'procurve', 'ios', 'iosxe', 'dnos', 'edgeswitch', 'routeros', 'comware', 'ironware', 'fastpath', 'h3c', '3com', 'extremexos'}
            switch_keywords = ['switch', '2910', 'procurve', 'catalyst', 'powerconnect', 'summit', 'aruba', 'j9147', 'j977', 'j978']

            for d in devices:
                d_id = d.get("device_id")
                if not d_id:
                    continue
                h_name = d.get("hostname", "N/A")
                sys_name = d.get("sysName") or h_name or f"Device {d_id}"
                os_str = str(d.get("os") or "").lower()
                hw_str = str(d.get("hardware") or "").lower()
                sys_lower = sys_name.lower()
                host_lower = h_name.lower()

                is_sw = (os_str in switch_os or
                         any(k in hw_str or k in sys_lower for k in switch_keywords) or
                         host_lower.startswith('sw') or '-sw' in host_lower or 'sw-' in host_lower or 'switch' in host_lower)

                device_map[d_id] = h_name
                device_names[d_id] = sys_name
                device_meta[d_id] = {
                    "is_switch": is_sw,
                    "os": d.get("os"),
                    "hardware": d.get("hardware"),
                    "community": d.get("community", "public")
                }
        except Exception as e:
            print(f"[BottleneckDetector] Erro ao carregar dispositivos: {e}")
        return device_map, device_names, device_meta

    def _get_zabbix_map(self):
        """Retorna mapa de IP -> Nome de host no Zabbix."""
        zabbix_map = {}
        if not self.zabbix:
            return zabbix_map
        try:
            hosts = self.zabbix.get_hosts()
            for h in hosts or []:
                name = h.get("name") or h.get("host")
                for iface in h.get("interfaces", []):
                    ip = iface.get("ip")
                    if ip:
                        zabbix_map[ip] = name
        except Exception as e:
            print(f"[BottleneckDetector] Erro ao obter mapa do Zabbix: {e}")
        return zabbix_map

    def resolve_connected_devices(self, items):
        """
        Resolve em lote o dispositivo conectado (quem está na porta) para cada interface.
        Hierarquia de resolução:
          1. monitored_infrastructure em config.json
          2. LLDP / CDP link (tabela links do LibreNMS)
          3. FDB / ARP (MAC address aprendido na porta + tabela ARP/IP + mapeamento Zabbix/DNS)
          4. ifAlias descritivo configurado na interface
        """
        if not items:
            return items

        config = ConfigService.load_config()
        monitored = {}
        for s in config.get("monitored_infrastructure", {}).get("switches", []):
            if s.get("ip") and s.get("port"):
                monitored[(s.get("ip"), s.get("port"))] = s

        zabbix_map = self._get_zabbix_map()

        port_ids = [p["port_id"] for p in items if p.get("port_id")]
        links_map = {}
        fdb_map = {}

        if port_ids and self.librenms and hasattr(self.librenms, "get_db_connection"):
            try:
                conn = self.librenms.get_db_connection()
                if conn:
                    with conn:
                        with conn.cursor() as cur:
                            fmt = ','.join(['%s'] * len(port_ids))
                            # 1. Links (LLDP/CDP)
                            cur.execute(f"""
                                SELECT l.local_port_id, d2.hostname, d2.sysName, d2.ip, p2.ifName, p2.ifDescr
                                FROM links l
                                JOIN devices d2 ON l.remote_device_id = d2.device_id
                                JOIN ports p2 ON l.remote_port_id = p2.port_id
                                WHERE l.local_port_id IN ({fmt})
                            """, tuple(port_ids))
                            for row in cur.fetchall():
                                l_pid, r_host, r_sys, r_ip, r_ifname, r_ifdescr = row
                                links_map[l_pid] = {
                                    "name": r_sys or r_host,
                                    "ip": r_host,
                                    "port": r_ifname or r_ifdescr
                                }

                            # 2. FDB + ARP
                            cur.execute(f"""
                                SELECT f.port_id, f.mac_address, ip.ipv4_address, d.sysName, d.hostname
                                FROM ports_fdb f
                                LEFT JOIN ipv4_mac ip ON f.mac_address = ip.mac_address
                                LEFT JOIN devices d ON ip.ipv4_address = d.hostname
                                WHERE f.port_id IN ({fmt})
                                ORDER BY f.updated_at DESC
                            """, tuple(port_ids))
                            for row in cur.fetchall():
                                f_pid, f_mac, f_ip, d_sys, d_host = row
                                if f_pid not in fdb_map:
                                    fdb_map[f_pid] = []
                                fdb_map[f_pid].append({
                                    "mac": f_mac,
                                    "ip": f_ip,
                                    "device_name": d_sys or d_host
                                })
            except Exception as e:
                print(f"[BottleneckDetector] Erro ao resolver FDB/links: {e}")

        for item in items:
            dev_ip = item.get("device_ip", "")
            p_id = item.get("port_id")
            p_name = item.get("port_name", "")
            p_alias = item.get("port_alias", "").strip()

            connected = None

            # 1. Infraestrutura pré-monitorada
            if (dev_ip, p_name) in monitored:
                m = monitored[(dev_ip, p_name)]
                connected = {
                    "type": "monitored_infra",
                    "name": m.get("dest_device"),
                    "port": m.get("dest_port"),
                    "ip": None,
                    "mac": None,
                    "label": f"{m.get('dest_device')} ({m.get('dest_port')})"
                }
            # 2. Link de vizinhança LLDP / CDP
            elif p_id in links_map:
                l = links_map[p_id]
                connected = {
                    "type": "lldp_neighbor",
                    "name": l["name"],
                    "port": l["port"],
                    "ip": l["ip"],
                    "mac": None,
                    "label": f"{l['name']} [{l['port']}]"
                }
            # 3. Tabela FDB (MAC aprendido) + ARP / IP
            elif p_id in fdb_map and fdb_map[p_id]:
                entries = fdb_map[p_id]
                unique_macs = list(dict.fromkeys(e["mac"] for e in entries if e.get("mac")))
                unique_ips = list(dict.fromkeys(e["ip"] for e in entries if e.get("ip")))

                if len(unique_macs) == 1:
                    mac = unique_macs[0]
                    formatted_mac = ':'.join(mac[i:i+2] for i in range(0, 12, 2)) if len(mac) == 12 else mac
                    ip = unique_ips[0] if unique_ips else None
                    name = None
                    if ip:
                        name = zabbix_map.get(ip)
                    if not name and entries[0].get("device_name"):
                        name = entries[0]["device_name"]

                    label = f"{ip} ({name})" if (ip and name) else (ip or formatted_mac)
                    connected = {
                        "type": "host",
                        "name": name,
                        "port": None,
                        "ip": ip,
                        "mac": formatted_mac,
                        "label": label
                    }
                elif len(unique_macs) > 1:
                    connected = {
                        "type": "multiple_hosts",
                        "count": len(unique_macs),
                        "sample_ips": unique_ips[:3],
                        "label": f"{len(unique_macs)} dispositivos conectados"
                    }

            # 4. Fallback para ifAlias da interface
            if not connected and p_alias and p_alias != p_name and not p_alias.isdigit():
                connected = {
                    "type": "alias",
                    "name": p_alias,
                    "port": None,
                    "ip": None,
                    "mac": None,
                    "label": p_alias
                }

            if not connected:
                connected = {
                    "type": "unknown",
                    "name": None,
                    "port": None,
                    "ip": None,
                    "mac": None,
                    "label": "Sem vizinho detectado"
                }

            item["connected_device"] = connected

        return items

    def detect_traffic_bottlenecks(self, settings=None, custom_threshold=None, ignore_virtual=None, force_refresh=False):
        """
        Detecta interfaces com alta utilização de banda (gargalos de capacidade).
        Calcula utilização % baseada no maior valor entre entrada e saída contra ifSpeed.
        """
        if settings is None:
            config = ConfigService.load_config()
            settings = config.get("bottlenecks_settings", {})

        warn_threshold = float(custom_threshold or settings.get("util_warning_threshold", 75.0))
        crit_threshold = float(settings.get("util_critical_threshold", 90.0))
        min_speed_mbps = float(settings.get("min_speed_mbps", 100.0))
        filter_virtual = settings.get("ignore_virtual_interfaces", True) if ignore_virtual is None else bool(ignore_virtual)

        bottlenecks = []
        if not self.librenms:
            return bottlenecks

        device_map, device_names, device_meta = self._get_device_maps(force_refresh=force_refresh)

        try:
            import time
            now_ts = int(time.time())
            ports = self.librenms.get_all_ports(force_refresh=force_refresh, ttl=10)
            for p in ports:
                # Apenas portas operacionais
                if p.get("ifOperStatus") != "up":
                    continue

                speed_bps = float(p.get("ifSpeed") or 0)
                if speed_bps <= 0:
                    continue

                speed_mbps = round(speed_bps / 1000000.0, 2)
                port_name = p.get("ifName") or p.get("ifDescr") or ""
                if_type = p.get("ifType") or "ethernet"
                is_virt = self.is_virtual_interface(port_name, if_type)

                # Filtragem de interfaces virtuais
                if filter_virtual and is_virt:
                    continue

                # Evita falsos positivos em interfaces de 10 Mbps virtuais/legadas
                if speed_mbps < min_speed_mbps and is_virt:
                    continue

                in_rate_bps = float(p.get("ifInOctets_rate") or 0) * 8.0
                out_rate_bps = float(p.get("ifOutOctets_rate") or 0) * 8.0
                max_rate_bps = max(in_rate_bps, out_rate_bps)

                util_pct = (max_rate_bps / speed_bps) * 100.0

                if util_pct >= warn_threshold:
                    d_id = p.get("device_id")
                    severity = "critical" if util_pct >= crit_threshold else "warning"
                    in_mbps = round(in_rate_bps / 1000000.0, 2)
                    out_mbps = round(out_rate_bps / 1000000.0, 2)
                    pct_rounded = round(util_pct, 2)

                    d_meta = device_meta.get(d_id, {})
                    poll_t = int(p.get("poll_time") or 0)
                    poll_age = (now_ts - poll_t) if poll_t > 0 else None

                    bottlenecks.append({
                        "type": "high_utilization",
                        "severity": severity,
                        "device_id": d_id,
                        "device_name": device_names.get(d_id, f"Device {d_id}"),
                        "device_ip": device_map.get(d_id, "N/A"),
                        "is_switch": d_meta.get("is_switch", False),
                        "snmp_community": d_meta.get("community", "public"),
                        "port_id": p.get("port_id"),
                        "if_index": p.get("ifIndex"),
                        "port_name": port_name,
                        "port_alias": p.get("ifAlias") or "",
                        "if_type": if_type,
                        "is_virtual": is_virt,
                        "speed_mbps": speed_mbps,
                        "in_rate_mbps": in_mbps,
                        "out_rate_mbps": out_mbps,
                        "util_pct": pct_rounded,
                        "poll_time": poll_t,
                        "poll_age_seconds": poll_age,
                        "details": f"Porta operando a {pct_rounded}% da capacidade ({speed_mbps} Mbps). Entrada: {in_mbps} Mbps, Saída: {out_mbps} Mbps."
                    })

            # Ordena decrescente pela maior taxa de utilização
            bottlenecks.sort(key=lambda x: x["util_pct"], reverse=True)

            # Resolve quem está conectado em cada porta
            self.resolve_connected_devices(bottlenecks)

        except Exception as e:
            print(f"[BottleneckDetector] Erro ao detectar gargalos de tráfego: {e}")
            raise

        return bottlenecks

    def detect_port_errors(self, settings=None, force_refresh=False):
        """
        Detecta erros físicos (CRC/FCS/InErrors/OutErrors) e descartes de fila (Buffer Discards).
        Prioriza taxa instantânea (erros/s) e delta no último ciclo de polling (5 min),
        eliminando falsos positivos de erros acumulados há meses.
        """
        if settings is None:
            config = ConfigService.load_config()
            settings = config.get("bottlenecks_settings", {})

        mode = settings.get("error_detection_mode", "rate_and_delta")
        min_delta = int(settings.get("error_min_delta", 5))
        crit_rate = float(settings.get("error_critical_rate", 10.0))
        disc_min_delta = int(settings.get("discard_min_delta", 50))

        error_ports = []
        if not self.librenms:
            return error_ports

        device_map, device_names, device_meta = self._get_device_maps(force_refresh=force_refresh)

        try:
            import time
            now_ts = int(time.time())
            ports = self.librenms.get_all_ports(force_refresh=force_refresh, ttl=10)
            for p in ports:
                in_err_rate = float(p.get("ifInErrors_rate") or 0)
                out_err_rate = float(p.get("ifOutErrors_rate") or 0)
                in_err_delta = int(p.get("ifInErrors_delta") or 0)
                out_err_delta = int(p.get("ifOutErrors_delta") or 0)
                in_err_total = int(p.get("ifInErrors") or 0)
                out_err_total = int(p.get("ifOutErrors") or 0)

                in_disc_rate = float(p.get("ifInDiscards_rate") or 0)
                out_disc_rate = float(p.get("ifOutDiscards_rate") or 0)
                in_disc_delta = int(p.get("ifInDiscards_delta") or 0)
                out_disc_delta = int(p.get("ifOutDiscards_delta") or 0)
                in_disc_total = int(p.get("ifInDiscards") or 0)
                out_disc_total = int(p.get("ifOutDiscards") or 0)

                total_err_rate = in_err_rate + out_err_rate
                total_err_delta = in_err_delta + out_err_delta
                total_disc_rate = in_disc_rate + out_disc_rate
                total_disc_delta = in_disc_delta + out_disc_delta
                total_err = in_err_total + out_err_total
                total_disc = in_disc_total + out_disc_total

                # Critérios de ativação
                has_active_errors = False
                has_active_discards = False

                if mode == "rate_and_delta":
                    if total_err_rate > 0 or total_err_delta >= min_delta:
                        has_active_errors = True
                    if total_disc_rate > 0 or total_disc_delta >= disc_min_delta:
                        has_active_discards = True
                else: # cumulative
                    if total_err >= 1000:
                        has_active_errors = True
                    if total_disc >= 5000:
                        has_active_discards = True

                if not (has_active_errors or has_active_discards):
                    continue

                d_id = p.get("device_id")
                port_name = p.get("ifName") or p.get("ifDescr") or ""
                speed = float(p.get("ifSpeed") or 0)
                speed_mbps = round(speed / 1000000.0, 2) if speed else "N/A"

                # Classificação de severidade e categoria
                if total_err_rate >= crit_rate or total_err_delta >= 100:
                    severity = "critical"
                    category = "crc_physical"
                    action = "Falha física contínua: verificar cabeamento estruturado, conector RJ-45 ou módulo GBIC/SFP."
                elif has_active_errors:
                    severity = "warning"
                    category = "crc_physical"
                    action = "Erros físicos no último ciclo: monitorar estabilidade do link e inspeção física se persistir."
                elif total_disc_delta >= disc_min_delta * 5 or total_disc_rate >= 50:
                    severity = "warning"
                    category = "buffer_drop"
                    action = "Descartes intensos de fila: verificar saturação momentânea (microbursts) ou QoS na porta."
                else:
                    severity = "info"
                    category = "buffer_drop"
                    action = "Descartes esporádicos de buffer de hardware (queda de pacotes por congestionamento breve)."

                details_parts = []
                if has_active_errors:
                    details_parts.append(f"Erros de Pacote: Taxa={round(total_err_rate, 1)}/s (Delta: +{total_err_delta} no ciclo, Total={total_err})")
                if has_active_discards:
                    details_parts.append(f"Descartes de Buffer: Taxa={round(total_disc_rate, 1)}/s (Delta: +{total_disc_delta} no ciclo, Total={total_disc})")

                d_meta = device_meta.get(d_id, {})
                poll_t = int(p.get("poll_time") or 0)
                poll_age = (now_ts - poll_t) if poll_t > 0 else None

                error_ports.append({
                    "type": "port_errors_discards",
                    "category": category,
                    "severity": severity,
                    "device_id": d_id,
                    "device_name": device_names.get(d_id, f"Device {d_id}"),
                    "device_ip": device_map.get(d_id, "N/A"),
                    "is_switch": d_meta.get("is_switch", False),
                    "snmp_community": d_meta.get("community", "public"),
                    "port_id": p.get("port_id"),
                    "if_index": p.get("ifIndex"),
                    "port_name": port_name,
                    "port_alias": p.get("ifAlias") or "",
                    "speed_mbps": speed_mbps,
                    "error_rate": round(total_err_rate, 2),
                    "error_delta": total_err_delta,
                    "in_errors": in_err_total,
                    "out_errors": out_err_total,
                    "discard_rate": round(total_disc_rate, 2),
                    "discard_delta": total_disc_delta,
                    "in_discards": in_disc_total,
                    "out_discards": out_disc_total,
                    "poll_time": poll_t,
                    "poll_age_seconds": poll_age,
                    "recommended_action": action,
                    "details": " | ".join(details_parts)
                })

            # Ordena primeiro por severidade (critical > warning > info), depois por taxa de erros/delta
            sev_order = {"critical": 0, "warning": 1, "info": 2}
            error_ports.sort(key=lambda x: (sev_order.get(x["severity"], 3), -x["error_rate"], -x["error_delta"], -x["discard_delta"]))

            # Resolve quem está conectado em cada porta
            self.resolve_connected_devices(error_ports)

        except Exception as e:
            print(f"[BottleneckDetector] Erro ao detectar erros de portas: {e}")
            raise

        return error_ports

    def detect_all(self, settings=None, force_refresh=False):
        """Retorna estrutura separada com gargalos de tráfego e erros físicos."""
        if settings is None:
            config = ConfigService.load_config()
            settings = config.get("bottlenecks_settings", {})

        traffic = self.detect_traffic_bottlenecks(settings, force_refresh=force_refresh)
        errors = self.detect_port_errors(settings, force_refresh=force_refresh)

        return {
            "bottlenecks": traffic,
            "errors": errors,
            "summary": {
                "bottlenecks_total": len(traffic),
                "bottlenecks_critical": sum(1 for b in traffic if b["severity"] == "critical"),
                "errors_total": len(errors),
                "errors_critical": sum(1 for e in errors if e["severity"] == "critical"),
                "errors_physical": sum(1 for e in errors if e["category"] == "crc_physical"),
                "errors_discards": sum(1 for e in errors if e["category"] == "buffer_drop")
            }
        }

    def detect_bottlenecks(self, util_threshold=80.0):
        """
        Método legado para manter retrocompatibilidade com código existente e testes.
        Retorna lista unificada de gargalos e erros.
        """
        traffic = self.detect_traffic_bottlenecks(custom_threshold=util_threshold)
        errors = self.detect_port_errors()
        return traffic + errors
