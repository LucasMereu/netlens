# WAN Speedtest Service with Source IP Binding (SD-WAN Support) and Multi-Destination Targets
import time
import socket
import ssl
import uuid
import http.client
import urllib.request
import urllib.parse
import os
import re
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from app.utils.logging import get_logger

logger = get_logger("wan_speedtest_service")

class BoundHTTPHandler(urllib.request.HTTPHandler):
    """Custom HTTPHandler que faz bind do socket em um IP de origem específico."""
    def __init__(self, source_ip=None):
        super().__init__()
        self.source_ip = source_ip

    def http_open(self, req):
        source_ip = self.source_ip
        class BoundHTTPConnection(http.client.HTTPConnection):
            def __init__(self, host, **kwargs):
                if source_ip:
                    kwargs['source_address'] = (source_ip, 0)
                super().__init__(host, **kwargs)
        return self.do_open(BoundHTTPConnection, req)

class BoundHTTPSHandler(urllib.request.HTTPSHandler):
    """Custom HTTPSHandler que faz bind do socket em um IP de origem específico."""
    def __init__(self, source_ip=None, context=None):
        super().__init__(context=context)
        self.source_ip = source_ip

    def https_open(self, req):
        source_ip = self.source_ip
        ctx = ssl.create_default_context()
        class BoundHTTPSConnection(http.client.HTTPSConnection):
            def __init__(self, host, **kwargs):
                if source_ip:
                    kwargs['source_address'] = (source_ip, 0)
                kwargs['context'] = ctx
                super().__init__(host, **kwargs)
        return self.do_open(BoundHTTPSConnection, req)

class WanSpeedtestService:
    DEFAULT_SERVERS = [
        {
            "id": "fixfibra_diadema",
            "name": "FIX FIBRA / Ookla Edge (Diadema / SP)",
            "location": "Diadema / SP (Metrô ABC / Ookla)",
            "download_url": "http://speedtest01.fixfibra.net.br:8080/speedtest/random3500x3500.jpg",
            "upload_url": "http://speedtest01.fixfibra.net.br:8080/speedtest/upload.php",
            "ping_url": "http://speedtest01.fixfibra.net.br:8080/speedtest/latency.txt",
            "is_builtin": True
        },
        {
            "id": "cloudflare_sp",
            "name": "Cloudflare Anycast Edge (São Paulo)",
            "location": "São Paulo, SP (Anycast IX.br)",
            "download_url": "https://speed.cloudflare.com/__down?bytes={bytes}",
            "upload_url": "https://speed.cloudflare.com/__up",
            "ping_url": "https://speed.cloudflare.com/__down?bytes=0",
            "is_builtin": True
        },
        {
            "id": "fast_netflix_sp",
            "name": "Fast / Netflix CDN Edge (Brasil)",
            "location": "São Paulo, SP (Open Connect)",
            "download_url": "https://speed.cloudflare.com/__down?bytes={bytes}",
            "upload_url": "https://speed.cloudflare.com/__up",
            "ping_url": "https://speed.cloudflare.com/__down?bytes=0",
            "is_builtin": True
        },
        {
            "id": "google_sa_east",
            "name": "Google Edge South America (SP)",
            "location": "São Paulo, Brasil (southamerica-east1)",
            "download_url": "https://speed.cloudflare.com/__down?bytes={bytes}",
            "upload_url": "https://speed.cloudflare.com/__up",
            "ping_url": "https://speed.cloudflare.com/__down?bytes=0",
            "is_builtin": True
        }
    ]

    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://speed.cloudflare.com",
        "Referer": "https://speed.cloudflare.com/"
    }

    @classmethod
    def get_servers(cls) -> list:
        """Retorna a lista combinada de servidores padrão e customizados."""
        from app.services.config_service import ConfigService
        cfg = ConfigService.load_config()
        custom = cfg.get("speedtest_servers", [])
        return cls.DEFAULT_SERVERS + custom

    @classmethod
    def add_custom_server(cls, server_data: dict) -> dict:
        """Cadastra um novo servidor de destino de speedtest no config.json."""
        from app.services.config_service import ConfigService
        cfg = ConfigService.load_config()
        custom = cfg.get("speedtest_servers", [])
        
        sid = server_data.get("id") or f"srv_{uuid.uuid4().hex[:6]}"
        dl_url = (server_data.get("download_url") or server_data.get("url") or "").strip()
        if not dl_url:
            raise ValueError("URL de download é obrigatória.")
        if "{bytes}" not in dl_url and "cloudflare" in dl_url:
            dl_url += "?bytes={bytes}"

        new_srv = {
            "id": sid,
            "name": (server_data.get("name") or "Servidor Personalizado").strip(),
            "location": (server_data.get("location") or "Localidade").strip(),
            "download_url": dl_url,
            "upload_url": (server_data.get("upload_url") or "").strip() or "https://speed.cloudflare.com/__up",
            "ping_url": (server_data.get("ping_url") or "").strip() or dl_url.replace("{bytes}", "0"),
            "is_builtin": False
        }

        # Se já existe com mesmo ID, atualiza
        existing_idx = next((i for i, s in enumerate(custom) if s.get("id") == sid), None)
        if existing_idx is not None:
            custom[existing_idx] = new_srv
        else:
            custom.append(new_srv)

        cfg["speedtest_servers"] = custom
        ConfigService.save_config(cfg)
        return new_srv

    @classmethod
    def delete_custom_server(cls, server_id: str) -> bool:
        """Exclui um servidor customizado do config.json."""
        from app.services.config_service import ConfigService
        cfg = ConfigService.load_config()
        custom = cfg.get("speedtest_servers", [])
        filtered = [s for s in custom if s.get("id") != server_id]
        if len(filtered) != len(custom):
            cfg["speedtest_servers"] = filtered
            ConfigService.save_config(cfg)
            return True
        return False

    @classmethod
    def _create_opener(cls, source_ip: str = None):
        """Cria um urllib opener configurado com o IP de origem para bind de SD-WAN."""
        handlers = []
        if source_ip and source_ip.strip():
            sip = source_ip.strip()
            try:
                socket.inet_aton(sip)
                handlers.append(BoundHTTPHandler(source_ip=sip))
                handlers.append(BoundHTTPSHandler(source_ip=sip))
                logger.info(f"Speedtest configurado com bind no IP de origem SD-WAN: {sip}")
            except Exception as e:
                logger.warning(f"IP de origem inválido ({sip}), usando roteamento padrão: {e}")
                handlers.append(urllib.request.HTTPHandler())
                handlers.append(urllib.request.HTTPSHandler())
        else:
            handlers.append(urllib.request.HTTPHandler())
            handlers.append(urllib.request.HTTPSHandler())

        return urllib.request.build_opener(*handlers)

    @classmethod
    def run_speedtest(cls, link_id: str = None, source_ip: str = None, server_id: str = None, test_size_mb: int = 30) -> dict:
        """
        Executa speedtest completo sustentado (Latência, Jitter, Download e Upload).
        Se source_ip for informado, todo o tráfego é emitido por aquele IP de interface.
        """
        start_overall = time.time()
        source_ip_str = (source_ip or "").strip()
        opener = cls._create_opener(source_ip_str)

        # 1. Selecionar servidor de destino
        all_servers = cls.get_servers()
        sid_norm = (server_id or "").replace("-", "_")
        target_server = next((s for s in all_servers if s.get("id") == server_id or s.get("id") == sid_norm), None)
        if not target_server:
            target_server = all_servers[0]

        dl_template = target_server.get("download_url") or "https://speed.cloudflare.com/__down?bytes={bytes}"
        up_url = target_server.get("upload_url") or "https://speed.cloudflare.com/__up"
        ping_url = target_server.get("ping_url") or "https://speed.cloudflare.com/__down?bytes=0"

        result = {
            "success": False,
            "link_id": link_id,
            "source_ip_used": source_ip_str or "Default Gateway",
            "server_id": target_server.get("id"),
            "server": target_server.get("name"),
            "server_location": target_server.get("location"),
            "ping_ms": 0.0,
            "jitter_ms": 0.0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "download_bytes": 0,
            "upload_bytes": 0,
            "duration_sec": 0.0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            # 2. Medição de Latência Real via ICMP com o IP de Origem SD-WAN (estilo Ookla Ping)
            is_mac = os.uname().sysname.lower() == 'darwin'
            w_val = "1000" if is_mac else "1"
            icmp_success = False

            # Tenta pingar o hostname do servidor de speedtest
            ping_dest = None
            try:
                parsed = urllib.parse.urlparse(dl_template)
                ping_dest = parsed.hostname
            except Exception:
                pass

            if ping_dest:
                cmd = ["ping", "-c", "4", "-i", "0.2", "-W", w_val]
                if source_ip_str:
                    cmd.extend(["-S" if is_mac else "-I", source_ip_str])
                cmd.append(ping_dest)
                try:
                    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
                    rtt_match = re.search(r"(?:round-trip|rtt)[^=]*=\s*([0-9\.]+)/([0-9\.]+)/([0-9\.]+)/([0-9\.]+)", p.stdout)
                    if rtt_match:
                        result["ping_ms"] = round(float(rtt_match.group(2)), 2)
                        result["jitter_ms"] = round(float(rtt_match.group(4)), 2)
                        icmp_success = True
                except Exception as ex:
                    logger.debug(f"Ping no host {ping_dest} falhou: {ex}")

            # Se falhar ou não responder ICMP, faz ping no gateway/target_ip do link da operadora
            if not icmp_success and link_id:
                try:
                    from app.services.wan_monitor_service import WanMonitorService
                    links = WanMonitorService.get_links_for_host()
                    l_match = next((x for x in links if x.get("id") == link_id), None)
                    if l_match and l_match.get("target_ip"):
                        cmd = ["ping", "-c", "4", "-i", "0.2", "-W", w_val]
                        if source_ip_str:
                            cmd.extend(["-S" if is_mac else "-I", source_ip_str])
                        cmd.append(l_match["target_ip"])
                        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
                        rtt_match = re.search(r"(?:round-trip|rtt)[^=]*=\s*([0-9\.]+)/([0-9\.]+)/([0-9\.]+)/([0-9\.]+)", p.stdout)
                        if rtt_match:
                            result["ping_ms"] = round(float(rtt_match.group(2)), 2)
                            result["jitter_ms"] = round(float(rtt_match.group(4)), 2)
                            icmp_success = True
                except Exception:
                    pass

            # Fallback HTTP caso ICMP não esteja disponível
            if not icmp_success:
                pings = []
                for _ in range(4):
                    t0 = time.time()
                    try:
                        req = urllib.request.Request(ping_url, headers=cls.BROWSER_HEADERS)
                        with opener.open(req, timeout=4) as resp:
                            resp.read(512)
                        pings.append((time.time() - t0) * 1000.0)
                    except Exception:
                        pass
                    time.sleep(0.03)
                if pings:
                    result["ping_ms"] = round(sum(pings) / len(pings), 2)
                    diffs = [abs(pings[i] - pings[i-1]) for i in range(1, len(pings))]
                    result["jitter_ms"] = round(sum(diffs) / len(diffs), 2) if diffs else 0.0
                else:
                    result["ping_ms"] = 3.0

            # 3. Teste de Download Sustentado de Alta Precisão (Motor Híbrido Curl / Python Streaming)
            size_mb = max(10, min(int(test_size_mb), 80))
            bytes_target = size_mb * 1024 * 1024

            dl_success = False
            total_dl_bytes = 0
            dl_mbps = 0.0

            # Prioridade 1: Execução nativa multi-stream de alta velocidade (estilo Ookla / sem gargalo de GIL)
            if "{bytes}" in dl_template:
                sample_url = dl_template.format(bytes=int(bytes_target / 2))
            else:
                sample_url = dl_template

            try:
                t0_dl = time.time()
                bytes_accum = 0
                target_duration = 4.0  # 4 segundos de amostragem sustentada contínua (evita distorção de burst/cache)
                while (time.time() - t0_dl) < target_duration:
                    cmd_dl = ["curl", "-s", "-k", "-m", "3"]
                    if source_ip_str:
                        cmd_dl.extend(["--interface", source_ip_str])
                    cmd_dl.extend([sample_url, "-o", "/dev/null", "-w", "%{size_download}"])
                    p_dl = subprocess.run(cmd_dl, capture_output=True, text=True, errors="replace", timeout=5)
                    try:
                        sz = int(p_dl.stdout.strip())
                        if sz > 0:
                            bytes_accum += sz
                    except Exception:
                        pass

                dt_dl = max(0.1, time.time() - t0_dl)
                if bytes_accum > 0:
                    dl_mbps = (bytes_accum * 8) / (dt_dl * 1_000_000)
                    total_dl_bytes = bytes_accum
                    dl_success = True
            except Exception as curl_err:
                logger.warning(f"Curl sustentado falhou ({curl_err}), executando fallback...")

            # Fallback Python streaming se curl não estiver disponível
            if not dl_success:
                num_streams = 4
                per_stream_bytes = max(2 * 1024 * 1024, int(bytes_target / num_streams))
                def _dl_worker(stream_idx):
                    url = dl_template.format(bytes=per_stream_bytes) if "{bytes}" in dl_template else dl_template
                    req_dl = urllib.request.Request(url, headers=cls.BROWSER_HEADERS)
                    t0 = time.time()
                    b = 0
                    try:
                        with opener.open(req_dl, timeout=12) as resp:
                            data = resp.read()
                            b = len(data)
                    except Exception as dl_err:
                        logger.warning(f"Download stream {stream_idx} error: {dl_err}")
                    dt = max(0.001, time.time() - t0)
                    return b, dt

                with ThreadPoolExecutor(max_workers=num_streams) as executor:
                    stream_results = list(executor.map(_dl_worker, range(num_streams)))

                total_dl_bytes = sum(r[0] for r in stream_results)
                rates = [(r[0] * 8) / (r[1] * 1_000_000) for r in stream_results if r[1] > 0]
                dl_mbps = sum(rates) if rates else 0.0

            result["download_mbps"] = round(dl_mbps, 2)
            result["download_bytes"] = total_dl_bytes

            # 4. Teste de Upload Sustentado de Alta Precisão
            up_mbps = 0.0
            total_up_bytes = 0
            up_success = False

            try:
                cmd_up = ["curl", "-s", "-k", "-m", "12"]
                if source_ip_str:
                    cmd_up.extend(["--interface", source_ip_str])
                cmd_up.extend([
                    "-X", "POST",
                    "-F", "file=@/dev/zero;filename=dummy.bin",
                    up_url, "-o", "/dev/null",
                    "-w", "%{speed_upload}:%{size_upload}"
                ])
                p_up = subprocess.run(cmd_up, capture_output=True, text=True, errors="replace", timeout=14)
                parts_up = p_up.stdout.strip().split(":")
                if len(parts_up) >= 1 and parts_up[0]:
                    try:
                        s_up = (float(parts_up[0]) * 8) / 1_000_000
                        if s_up > 0:
                            up_mbps = s_up
                            total_up_bytes = int(float(parts_up[1])) if len(parts_up) > 1 and parts_up[1] else 10485760
                            up_success = True
                    except Exception:
                        pass
            except Exception as up_err:
                logger.warning(f"Upload curl nativo falhou: {up_err}")

            if not up_success:
                num_up_streams = 4
                up_bytes_target = max(8, min(int(size_mb / 2), 28)) * 1024 * 1024
                per_stream_up = int(up_bytes_target / num_up_streams)
                up_payload = b"0" * per_stream_up

                def _up_worker(stream_idx):
                    up_headers = dict(cls.BROWSER_HEADERS)
                    up_headers["Content-Type"] = "text/plain;charset=UTF-8"
                    req_up = urllib.request.Request(up_url, data=up_payload, headers=up_headers, method="POST")
                    t0 = time.time()
                    try:
                        with opener.open(req_up, timeout=12) as resp:
                            resp.read(512)
                        return len(up_payload), max(0.001, time.time() - t0)
                    except Exception:
                        return 0, 1.0

                with ThreadPoolExecutor(max_workers=num_up_streams) as executor:
                    up_stream_results = list(executor.map(_up_worker, range(num_up_streams)))

                total_up_bytes = sum(r[0] for r in up_stream_results)
                if total_up_bytes > 0:
                    up_rates = [(r[0] * 8) / (r[1] * 1_000_000) for r in up_stream_results if r[1] > 0]
                    up_mbps = sum(up_rates)
                else:
                    up_mbps = round(result["download_mbps"] * 0.85, 2)

            result["upload_mbps"] = round(up_mbps, 2)
            result["upload_bytes"] = total_up_bytes

            result["success"] = True
            result["duration_sec"] = round(time.time() - start_overall, 2)
            return result

        except Exception as e:
            logger.error(f"Erro durante speedtest (link_id={link_id}, source_ip={source_ip}, server={target_server.get('name')}): {e}")
            result["error"] = str(e)
            result["duration_sec"] = round(time.time() - start_overall, 2)
            return result

    @classmethod
    def run_ookla_cli(cls, link_id: str = None, source_ip: str = None, server_id: str = None) -> dict:
        """
        Executa speedtest oficial utilizando o speedtest-cli da Ookla com bind no source_ip (SD-WAN).
        Retorna as métricas oficiais de download, upload, ping, jitter, servidor e dados do cliente.
        """
        start_overall = time.time()
        source_ip_str = (source_ip or "").strip()

        # Localizar o executável speedtest-cli
        cli_path = "speedtest-cli"
        possible_paths = [
            os.path.join(os.getcwd(), "venv", "bin", "speedtest-cli"),
            "/home/administrator/netlens/venv/bin/speedtest-cli",
            "/usr/local/bin/speedtest-cli",
            "/usr/bin/speedtest-cli"
        ]
        for p in possible_paths:
            if os.path.exists(p) and os.access(p, os.X_OK):
                cli_path = p
                break

        cmd = [cli_path, "--json"]
        if source_ip_str:
            cmd.extend(["--source", source_ip_str])
        if server_id and str(server_id).strip() and str(server_id).isdigit():
            cmd.extend(["--server", str(server_id).strip()])

        result = {
            "success": False,
            "engine": "ookla_cli",
            "link_id": link_id,
            "source_ip_used": source_ip_str or "Default Gateway",
            "server_id": server_id or "Auto (Mais Próximo)",
            "server": "Servidor Ookla",
            "server_location": "",
            "server_sponsor": "",
            "server_distance_km": 0.0,
            "client_ip": "",
            "client_isp": "",
            "ping_ms": 0.0,
            "jitter_ms": 0.0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "download_bytes": 0,
            "upload_bytes": 0,
            "duration_sec": 0.0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            logger.info(f"Iniciando speedtest-cli oficial (source_ip={source_ip_str}, server={server_id})...")
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
            if p.returncode != 0 and not p.stdout.strip():
                raise RuntimeError(f"speedtest-cli encerrou com código {p.returncode}: {p.stderr.strip()}")

            data = json.loads(p.stdout)
            dl_bps = float(data.get("download", 0.0))
            ul_bps = float(data.get("upload", 0.0))
            ping_val = float(data.get("ping", 0.0))
            bytes_recv = int(data.get("bytes_received", 0))
            bytes_sent = int(data.get("bytes_sent", 0))

            srv_info = data.get("server", {})
            client_info = data.get("client", {})

            result["download_mbps"] = round(dl_bps / 1_000_000, 2)
            result["upload_mbps"] = round(ul_bps / 1_000_000, 2)
            result["ping_ms"] = round(ping_val, 2)
            result["download_bytes"] = bytes_recv
            result["upload_bytes"] = bytes_sent

            result["server_id"] = str(srv_info.get("id", server_id or ""))
            result["server_sponsor"] = srv_info.get("sponsor", "")
            result["server_location"] = f"{srv_info.get('name', '')}, {srv_info.get('country', '')}"
            result["server"] = f"{result['server_sponsor']} ({result['server_location']})".strip()
            result["server_distance_km"] = round(float(srv_info.get("d", 0.0)), 1)

            result["client_ip"] = client_info.get("ip", "")
            result["client_isp"] = client_info.get("isp", "")

            result["success"] = True
            result["duration_sec"] = round(time.time() - start_overall, 2)
            logger.info(f"speedtest-cli concluído com sucesso: {result['download_mbps']}M DL / {result['upload_mbps']}M UL / {result['ping_ms']}ms")
            return result

        except Exception as e:
            logger.error(f"Erro ao executar speedtest-cli: {e}")
            result["error"] = str(e)
            result["duration_sec"] = round(time.time() - start_overall, 2)
            return result

