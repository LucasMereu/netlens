# WAN Link Quality & Degradation Monitoring Service
import os
import re
import time
import subprocess
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from app.utils.logging import get_logger

logger = get_logger("wan_monitor_service")

class WanMonitorService:
    _cache = None
    _cache_time = 0
    CACHE_TTL = 15  # segundos
    _metrics_history = {}  # link_id -> deque(maxlen=30)

    # Definição dos links WAN e circuitos de telecom corporativos
    WAN_LINKS = [
        {
            "id": "vivo",
            "name": "Link Vivo (Port 7)",
            "provider": "Telefônica / Vivo",
            "interface_name": "Port7_VIVO",
            "target_ip": "10.99.0.7",
            "fallback_probes": ["8.8.8.8", "1.1.1.1"],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 5.0,
            "type": "WAN",
            "appliance_host": "10.1.1.2"
        },
        {
            "id": "intelig",
            "name": "Link Intelig / TIM (Port 8)",
            "provider": "TIM Brasil / Intelig",
            "interface_name": "Port8_INTELIG",
            "target_ip": "10.99.0.8",
            "fallback_probes": ["8.8.4.4", "1.0.0.1"],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 5.0,
            "type": "WAN",
            "appliance_host": "10.1.1.2"
        },
        {
            "id": "l2l_jk",
            "name": "Link L2L JK Alpha 9 (Port 2)",
            "provider": "Lan-to-Lan Dedicado",
            "interface_name": "Port2_L2L_JK_ALPHA9",
            "target_ip": "10.99.0.2",
            "fallback_probes": [],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 2.0,
            "type": "L2L",
            "appliance_host": "10.1.1.2"
        },
        {
            "id": "bsb_lan_vpn",
            "name": "Túnel VPN Matriz - Brasília (Port 1)",
            "provider": "Rede Corporativa / VPN Brasília",
            "interface_name": "Port1",
            "target_ip": "10.61.0.250",
            "fallback_probes": [],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 20.0,
            "type": "INTER-SITE",
            "appliance_host": "10.61.0.250"
        },
        {
            "id": "bsb_nwi",
            "name": "Link NWI Telecom (Port 2)",
            "provider": "NWI Telecomunicações",
            "interface_name": "Port2-BSB - NWI Telecom",
            "target_ip": "10.61.0.250",
            "fallback_probes": ["8.8.8.8", "1.1.1.1"],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 18.0,
            "type": "WAN",
            "appliance_host": "10.61.0.250"
        },
        {
            "id": "bsb_starlink",
            "name": "Link Starlink (Port 3)",
            "provider": "SpaceX / Starlink",
            "interface_name": "Port3_StarLink",
            "target_ip": "10.61.0.250",
            "fallback_probes": ["8.8.4.4"],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 45.0,
            "type": "WAN",
            "appliance_host": "10.61.0.250"
        },
        {
            "id": "bsb_n1",
            "name": "Link N1 Internet (Port 4)",
            "provider": "N1 Internet",
            "interface_name": "Port4- N1-INTERNET",
            "target_ip": "45.172.162.40",
            "fallback_probes": ["1.0.0.1"],
            "expected_speed": "1000 Mbps - Full Duplex",
            "baseline_rtt_ms": 25.0,
            "type": "WAN",
            "appliance_host": "10.61.0.250"
        }
    ]

    @classmethod
    def clear_cache(cls):
        """Invalida o cache de métricas e status de links para atualização imediata."""
        if hasattr(cls, "_cache_dict") and isinstance(cls._cache_dict, dict):
            cls._cache_dict.clear()
        cls._cache = None
        cls._cache_time = 0

    @classmethod
    def get_links_for_host(cls, host: str = None) -> list:
        # Carregar dinamicamente do config.json se disponível
        from app.services.config_service import ConfigService
        cfg = ConfigService.load_config()
        configured_links = cfg.get("wan_links") or cls.WAN_LINKS

        if not host or host == "all":
            return configured_links

        # Se for matriz (10.1.1.2), traz os links locais da matriz (appliance_host == 10.1.1.2 ou vazio/None)
        if host == "10.1.1.2":
            return [l for l in configured_links if l.get("appliance_host") in (None, "", "10.1.1.2")]

        # Para qualquer outro firewall específico (ex: 10.61.0.250 Brasília ou 10.11.0.253 STR):
        # Traz APENAS os links vinculados explicitamente a ele.
        # NUNCA fazer fallback para a matriz, evitando vazamento ou exclusão cruzada de cards!
        return [l for l in configured_links if l.get("appliance_host") == host]

    @classmethod
    def probe_single_link(cls, link_id: str, host: str = None) -> dict:
        """Executa sondagem isolada em tempo real para um único link WAN."""
        links = cls.get_links_for_host(host)
        target_link = next((l for l in links if l.get("id") == link_id), None)
        if not target_link:
            # Tentar achar em todos os links configurados
            from app.services.config_service import ConfigService
            cfg = ConfigService.load_config()
            all_links = cfg.get("wan_links") or cls.WAN_LINKS
            target_link = next((l for l in all_links if l.get("id") == link_id), None)

        if not target_link:
            return {"success": False, "error": f"Link '{link_id}' não encontrado"}

        # Executa disparo ICMP com 4 pacotes respeitando source_ip (SD-WAN bind)
        probe = cls._probe_icmp(target_link["target_ip"], count=4, timeout_sec=4, source_ip=target_link.get("source_ip"))
        sla = cls._classify_sla(probe, target_link.get("baseline_rtt_ms", 10.0))

        # Tentar obter velocidade negociada via Sophos
        negotiated_speed = target_link.get("expected_speed", "1000 Mbps - Full Duplex")
        try:
            from app.services.sophos_service import SophosService
            target_app_host = target_link.get("appliance_host") or host or "10.1.1.2"
            sophos_data = SophosService.get_firewall_overview(host=target_app_host)
            if sophos_data.get("success") and sophos_data.get("interfaces"):
                for iface in sophos_data["interfaces"]:
                    if iface.get("name") == target_link.get("interface_name"):
                        negotiated_speed = iface.get("status_detail") or negotiated_speed
                        break
        except Exception:
            pass

        cls.record_metric_point(target_link["id"], probe)

        return {
            "success": True,
            "link": {
                "id": target_link["id"],
                "name": target_link["name"],
                "provider": target_link["provider"],
                "type": target_link.get("type", "WAN"),
                "target_ip": target_link["target_ip"],
                "source_ip": target_link.get("source_ip", ""),
                "interface_name": target_link.get("interface_name", ""),
                "physical_status": "UP" if probe["alive"] else "DOWN",
                "negotiated_speed": negotiated_speed,
                "metrics": probe,
                "sla": sla,
                "history": cls.get_link_history(target_link["id"])
            }
        }

    @classmethod
    def _probe_icmp(cls, ip: str, count: int = 4, timeout_sec: int = 4, source_ip: str = None) -> dict:
        """Executa disparo ICMP controlado para coletar RTT, Perda e Jitter."""
        is_mac = os.uname().sysname.lower() == 'darwin'
        w_val = "1000" if is_mac else "1"

        cmd = ["ping", "-c", str(count), "-i", "0.2", "-W", w_val]
        if source_ip and source_ip.strip():
            sip = source_ip.strip()
            if is_mac:
                cmd.extend(["-S", sip])
            else:
                cmd.extend(["-I", sip])
        cmd.append(ip)
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec)
            out = p.stdout

            # 1. Perda de pacotes
            loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
            loss_pct = float(loss_match.group(1)) if loss_match else (0.0 if p.returncode == 0 else 100.0)

            # 2. Estatísticas RTT (min/avg/max/stddev ou mdev)
            rtt_match = re.search(r"(?:round-trip|rtt)[^=]*=\s*([0-9\.]+)/([0-9\.]+)/([0-9\.]+)/([0-9\.]+)", out)
            if rtt_match:
                rtt_min = float(rtt_match.group(1))
                rtt_avg = float(rtt_match.group(2))
                rtt_max = float(rtt_match.group(3))
                jitter = float(rtt_match.group(4))
            else:
                if loss_pct < 100.0:
                    rtt_min = rtt_avg = rtt_max = jitter = 1.0
                else:
                    rtt_min = rtt_avg = rtt_max = jitter = 0.0

            return {
                "alive": loss_pct < 100.0,
                "packet_loss": loss_pct,
                "rtt_min": round(rtt_min, 2),
                "rtt_avg": round(rtt_avg, 2),
                "rtt_max": round(rtt_max, 2),
                "jitter": round(jitter, 2)
            }
        except Exception as e:
            logger.warning(f"Falha no probe ICMP para {ip}: {e}")
            return {
                "alive": False,
                "packet_loss": 100.0,
                "rtt_min": 0.0,
                "rtt_avg": 0.0,
                "rtt_max": 0.0,
                "jitter": 0.0
            }

    @classmethod
    def _classify_sla(cls, probe_result: dict, baseline_rtt: float) -> dict:
        """Determina o estado de degradação com base na perda, latência e jitter."""
        if not probe_result["alive"] or probe_result["packet_loss"] >= 100.0:
            return {
                "status": "DOWN",
                "label": "Fora do Ar",
                "color": "#ef4444",
                "badge": "danger",
                "icon": "fa-circle-xmark",
                "alert": True,
                "reason": "Link sem resposta a sondagens ICMP (100% de perda)"
            }

        loss = probe_result["packet_loss"]
        avg = probe_result["rtt_avg"]
        jitter = probe_result["jitter"]

        # Degradação Crítica
        if loss > 5.0 or avg > (baseline_rtt * 4.0) or avg > 180.0:
            reasons = []
            if loss > 5.0: reasons.append(f"Perda de pacotes crítica: {loss}%")
            if avg > 180.0 or avg > (baseline_rtt * 4.0): reasons.append(f"Latência estourada: {avg}ms (base: {baseline_rtt}ms)")
            return {
                "status": "CRITICAL",
                "label": "Degradação Crítica",
                "color": "#f43f5e",
                "badge": "danger",
                "icon": "fa-triangle-exclamation",
                "alert": True,
                "reason": " • ".join(reasons)
            }

        # Degradação Moderada / Alerta
        if loss > 0.0 or avg > (baseline_rtt * 2.0) or jitter > 15.0:
            reasons = []
            if loss > 0.0: reasons.append(f"Perda intermitente: {loss}%")
            if avg > (baseline_rtt * 2.0): reasons.append(f"Latência elevada: {avg}ms")
            if jitter > 15.0: reasons.append(f"Oscilação/Jitter: {jitter}ms")
            return {
                "status": "DEGRADED",
                "label": "Degradação Moderada",
                "color": "#f59e0b",
                "badge": "warning",
                "icon": "fa-circle-exclamation",
                "alert": True,
                "reason": " • ".join(reasons)
            }

        # Saudável / Excelente
        return {
            "status": "HEALTHY",
            "label": "Saudável / Normal",
            "color": "#10b981",
            "badge": "success",
            "icon": "fa-circle-check",
            "alert": False,
            "reason": f"Qualidade 100% estável (RTT: {avg}ms, perda: 0%)"
        }

    @classmethod
    def record_metric_point(cls, link_id: str, probe: dict):
        """Armazena ponto de telemetria no ring buffer em memória (últimos 30 pontos)."""
        if link_id not in cls._metrics_history:
            cls._metrics_history[link_id] = deque(maxlen=30)
        cls._metrics_history[link_id].append({
            "timestamp": time.strftime("%H:%M:%S"),
            "rtt_avg": probe.get("rtt_avg", 0.0),
            "jitter": probe.get("jitter", 0.0),
            "packet_loss": probe.get("packet_loss", 0.0),
            "alive": probe.get("alive", False)
        })

    @classmethod
    def get_link_history(cls, link_id: str) -> list:
        """Retorna a lista cronológica de métricas do link."""
        return list(cls._metrics_history.get(link_id, []))

    @classmethod
    def get_wan_health(cls, force: bool = False, host: str = None) -> dict:
        """Executa probe concorrente dos links WAN e retorna diagnóstico."""
        now = time.time()
        cache_key = f"wan_{host or 'all'}"
        if not hasattr(cls, "_cache_dict"):
            cls._cache_dict = {}

        if not force and cache_key in cls._cache_dict:
            entry = cls._cache_dict[cache_key]
            if now - entry["time"] < cls.CACHE_TTL:
                return entry["data"]

        target_links = cls.get_links_for_host(host)

        # Obter dados de interfaces do Sophos para enriquecer velocidade e estado físico
        from app.services.sophos_service import SophosService
        sophos_data = SophosService.get_firewall_overview(host=host)
        ifaces_map = {}
        if sophos_data.get("success") and sophos_data.get("interfaces"):
            for i in sophos_data["interfaces"]:
                ifaces_map[i["name"]] = i

        def probe_single_link(link):
            probe = cls._probe_icmp(link["target_ip"], source_ip=link.get("source_ip"))
            sla = cls._classify_sla(probe, link.get("baseline_rtt_ms", 10.0))
            cls.record_metric_point(link["id"], probe)
            
            # Cruzar com interface do Sophos se existir
            iface_info = ifaces_map.get(link["interface_name"], {})
            negotiated_speed = iface_info.get("status_detail") or link["expected_speed"]
            phy_status = iface_info.get("status", "UP" if probe["alive"] else "DOWN")

            return {
                "id": link["id"],
                "name": link["name"],
                "provider": link["provider"],
                "type": link["type"],
                "target_ip": link["target_ip"],
                "source_ip": link.get("source_ip", ""),
                "interface_name": link.get("interface_name", ""),
                "physical_status": phy_status,
                "negotiated_speed": negotiated_speed,
                "metrics": probe,
                "sla": sla,
                "history": cls.get_link_history(link["id"])
            }

        with ThreadPoolExecutor(max_workers=max(1, len(target_links))) as executor:
            results = list(executor.map(probe_single_link, target_links))

        total_links = len(results)
        healthy_count = len([r for r in results if r["sla"]["status"] == "HEALTHY"])
        degraded_count = len([r for r in results if r["sla"]["status"] in ("DEGRADED", "CRITICAL")])
        down_count = len([r for r in results if r["sla"]["status"] == "DOWN"])

        overall_status = "HEALTHY"
        if down_count > 0 or any(r["sla"]["status"] == "CRITICAL" for r in results):
            overall_status = "CRITICAL"
        elif degraded_count > 0:
            overall_status = "DEGRADED"

        data = {
            "success": True,
            "host": host or "all",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total": total_links,
                "healthy": healthy_count,
                "degraded": degraded_count,
                "down": down_count,
                "overall_status": overall_status
            },
            "links": results
        }

        cls._cache_dict[cache_key] = {"time": now, "data": data}
        return data

    @classmethod
    def run_extended_ping(cls, target_ip: str, count: int = 15, timeout_sec: int = 20, baseline_rtt: float = 15.0, source_ip: str = None) -> dict:
        """Executa ping estendido com contagem de pacotes, medindo cada RTT individualmente."""
        count = max(5, min(int(count), 50))
        is_mac = os.uname().sysname.lower() == 'darwin'
        w_val = "2000" if is_mac else "2"
        cmd = ["ping", "-c", str(count), "-W", w_val]
        if source_ip and source_ip.strip():
            sip = source_ip.strip()
            if is_mac:
                cmd.extend(["-S", sip])
            else:
                cmd.extend(["-I", sip])
        cmd.append(target_ip)
        start_ts = time.time()
        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_sec
            )
            out = p.stdout
            
            samples = []
            for line in out.splitlines():
                m = re.search(r"icmp_seq=(\d+).*time=([0-9\.]+)\s*ms", line)
                if m:
                    samples.append({
                        "seq": int(m.group(1)) + 1,
                        "time_ms": float(m.group(2)),
                        "status": "OK"
                    })
                    
            loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
            loss_pct = float(loss_match.group(1)) if loss_match else (0.0 if p.returncode == 0 else 100.0)

            rtt_match = re.search(r"(?:round-trip|rtt)[^=]*=\s*([0-9\.]+)/([0-9\.]+)/([0-9\.]+)/([0-9\.]+)", out)
            if rtt_match:
                rtt_min = float(rtt_match.group(1))
                rtt_avg = float(rtt_match.group(2))
                rtt_max = float(rtt_match.group(3))
                jitter = float(rtt_match.group(4))
            else:
                if samples:
                    times = [s["time_ms"] for s in samples]
                    rtt_min = min(times)
                    rtt_avg = sum(times) / len(times)
                    rtt_max = max(times)
                    diffs = [abs(times[i] - times[i-1]) for i in range(1, len(times))]
                    jitter = sum(diffs) / len(diffs) if diffs else 0.0
                else:
                    rtt_min = rtt_avg = rtt_max = jitter = 0.0

            received_seqs = {s["seq"] for s in samples}
            timeline = []
            for seq in range(1, count + 1):
                if seq in received_seqs:
                    s = next(x for x in samples if x["seq"] == seq)
                    timeline.append(s)
                else:
                    timeline.append({
                        "seq": seq,
                        "time_ms": None,
                        "status": "TIMEOUT"
                    })

            probe_result = {
                "alive": len(samples) > 0,
                "packet_loss": loss_pct,
                "rtt_min": round(rtt_min, 2),
                "rtt_avg": round(rtt_avg, 2),
                "rtt_max": round(rtt_max, 2),
                "jitter": round(jitter, 2)
            }
            sla = cls._classify_sla(probe_result, baseline_rtt)

            return {
                "success": True,
                "target_ip": target_ip,
                "count": count,
                "packets_transmitted": count,
                "packets_received": len(samples),
                "packet_loss": loss_pct,
                "rtt_min": round(rtt_min, 2),
                "rtt_avg": round(rtt_avg, 2),
                "rtt_max": round(rtt_max, 2),
                "jitter": round(jitter, 2),
                "timeline": timeline,
                "sla": sla,
                "duration_sec": round(time.time() - start_ts, 2)
            }
        except Exception as e:
            logger.error(f"Erro ao executar extended ping para {target_ip}: {e}")
            return {
                "success": False,
                "target_ip": target_ip,
                "error": str(e),
                "count": count,
                "packets_transmitted": count,
                "packets_received": 0,
                "packet_loss": 100.0,
                "rtt_min": 0.0,
                "rtt_avg": 0.0,
                "rtt_max": 0.0,
                "jitter": 0.0,
                "timeline": [],
                "sla": {
                    "status": "DOWN",
                    "label": "Falha de Teste",
                    "color": "#ef4444",
                    "badge": "danger",
                    "icon": "fa-circle-xmark",
                    "alert": True,
                    "reason": f"Erro de execução: {str(e)}"
                },
                "duration_sec": round(time.time() - start_ts, 2)
            }
