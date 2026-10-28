import os
import re
import time
import platform
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

class PingMonitor:
    def __init__(self, targets=None, interval=3, max_history=10, simulation_mode=False):
        if targets is None:
            config = {}
            try:
                from app.services.config_service import ConfigService
                config = ConfigService.load_config()
            except Exception:
                pass
            cfg_targets = config.get("ping_targets", {})
            if cfg_targets:
                self.targets = {ip: (data["name"] if isinstance(data, dict) else str(data)) for ip, data in cfg_targets.items()}
                self.groups = {ip: (data.get("group", "data_plane") if isinstance(data, dict) else "data_plane") for ip, data in cfg_targets.items()}
            else:
                self.targets = {}
                self.groups = {}
        else:
            self.targets = {}
            self.groups = {}
            for ip, val in targets.items():
                if isinstance(val, dict):
                    self.targets[ip] = val.get("name", ip)
                    self.groups[ip] = val.get("group", "data_plane")
                else:
                    self.targets[ip] = str(val)
                    name_lower = str(val).lower()
                    if "ptp" in name_lower or "gerência" in name_lower or ("mgmt" in name_lower and "eth" not in name_lower):
                        self.groups[ip] = "control_plane"
                    else:
                        self.groups[ip] = "data_plane"

        self.interval = interval
        self.max_history = max_history
        self.simulation_mode = simulation_mode
        self.sim_tick = 0
        self.history = {ip: [] for ip in self.targets}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.alerts = []

        # Executa uma coleta inicial rápida para preencher o painel imediatamente
        print(f"[PingMonitor] Inicializando (simulação={self.simulation_mode})...")
        self._ping_all()

    def _ping_ip(self, ip):
        if self.simulation_mode:
            # Simula intermitência periódica a cada 20 ticks, durando 4 ticks
            # Control plane nós caem (100% loss)
            # Data plane nós funcionam normalmente
            cycle = self.sim_tick % 20
            is_failing = (8 <= cycle < 12)
            
            import random
            group = self.groups.get(ip, "data_plane")
            if is_failing and group == "control_plane":
                return 0.0, 100.0
            
            if group == "control_plane":
                return round(random.uniform(0.3, 2.0), 2), 0.0
            else:
                return round(random.uniform(0.2, 0.8), 2), 0.0

        system_name = platform.system().lower()
        if system_name == "windows":
            cmd = ["ping", "-n", "1", "-w", "1000", ip]
        elif system_name == "darwin":  # macOS
            cmd = ["ping", "-c", "1", "-t", "1", ip]
        else:  # Linux
            cmd = ["ping", "-c", "1", "-W", "1", ip]

        try:
            start_time = time.time()
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                timeout=1.5
            )
            duration = (time.time() - start_time) * 1000.0

            if result.returncode == 0:
                # Extrai a latência do output do ping
                match = re.search(r"time=([\d.]+)\s*ms", result.stdout)
                if match:
                    latency = float(match.group(1))
                else:
                    latency = round(duration, 2)
                return latency, 0.0  # 0% de perda
            else:
                return 0.0, 100.0  # 100% de perda
        except subprocess.TimeoutExpired:
            return 0.0, 100.0
        except Exception:
            return 0.0, 100.0

    def _ping_all(self):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ips = list(self.targets.keys())
        if not ips:
            with self.lock:
                self.alerts = []
            return

        if self.simulation_mode:
            results = [self._ping_ip(ip) for ip in ips]
            self.sim_tick += 1
        else:
            # Executa os pings em paralelo para evitar gargalo de timeouts
            with ThreadPoolExecutor(max_workers=len(ips)) as executor:
                results = list(executor.map(self._ping_ip, ips))

        with self.lock:
            for ip, (latency, loss) in zip(ips, results):
                ip_history = self.history[ip]
                ip_history.append({
                    "timestamp": timestamp,
                    "latency": latency,
                    "loss": loss
                })
                # Limita ao tamanho máximo
                if len(ip_history) > self.max_history:
                    ip_history.pop(0)

            # Executa a análise de correlação
            self._analyze_intermittency()

    def _analyze_intermittency(self):
        # Média de perda recente (últimas 5 amostras) para cada IP
        loss_stats = {}
        latency_stats = {}
        for ip in self.targets:
            history_slice = self.history[ip][-5:]
            if history_slice:
                loss_stats[ip] = sum(h["loss"] for h in history_slice) / len(history_slice)
                latencies = [h["latency"] for h in history_slice if h["loss"] == 0.0]
                latency_stats[ip] = sum(latencies) / len(latencies) if latencies else 0.0
            else:
                loss_stats[ip] = 0.0
                latency_stats[ip] = 0.0

        # Regra de Correlação Genérica:
        # Se os nós do grupo control_plane tiverem perda significativa (>=20%),
        # mas os nós do grupo data_plane estiverem operando normalmente (perda < 20%).
        cp_ips = [ip for ip, grp in self.groups.items() if grp == "control_plane" and ip in self.targets]
        dp_ips = [ip for ip, grp in self.groups.items() if grp == "data_plane" and ip in self.targets]

        if not cp_ips:
            self.alerts = []
            return

        cp_losses = [loss_stats.get(ip, 0.0) for ip in cp_ips]
        dp_losses = [loss_stats.get(ip, 0.0) for ip in dp_ips] if dp_ips else [0.0]

        avg_cp_loss = sum(cp_losses) / len(cp_losses) if cp_losses else 0.0
        avg_dp_loss = sum(dp_losses) / len(dp_losses) if dp_losses else 0.0

        cp_last_failed = any(self.history[ip] and self.history[ip][-1]["loss"] == 100.0 for ip in cp_ips)

        is_intermittent = (
            (avg_cp_loss >= 20.0 or cp_last_failed) and
            (avg_dp_loss < 20.0)
        )

        new_alerts = []
        if is_intermittent:
            dp_lat_strs = [f"{self.targets.get(ip, ip)}: {latency_stats.get(ip, 0.0):.2f} ms" for ip in dp_ips]
            cp_ip_names = [f"{self.targets.get(ip, ip)} ({ip})" for ip in cp_ips]
            dp_summary = " | ".join(dp_lat_strs) if dp_lat_strs else "Normal"
            
            new_alerts.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "severity": "critical",
                "alert_type": "control_plane_intermittency",
                "title": "Intermitência no Plano de Controle (Control Plane)",
                "description": (
                    f"Detectada perda de pacotes e alta latência nos nós de Control Plane: {', '.join(cp_ip_names)}. "
                    f"No entanto, o tráfego de trânsito (data plane) está operando normalmente ({dp_summary}). "
                    "Isso indica congestionamento, pico de CPU ou instabilidade no Plano de Controle, "
                    "sem afetar o tráfego de dados passante."
                ),
                "metrics": {
                    # Canonical generic metrics
                    "avg_control_plane_loss": round(avg_cp_loss, 2),
                    "avg_data_plane_loss": round(avg_dp_loss, 2),
                    "individual_losses": {ip: round(loss_stats.get(ip, 0.0), 2) for ip in self.targets},
                    # Compatibility aliases for legacy UI/clients
                    "dell_mgmt_loss": round(loss_stats.get("10.11.0.249", avg_cp_loss), 2),
                    "dell_ptp_loss": round(loss_stats.get("10.1.1.1", avg_cp_loss), 2),
                    "sophos_loss": round(loss_stats.get("10.1.1.2", avg_dp_loss), 2),
                    "dell_eth_loss": round(loss_stats.get("10.11.0.248", avg_dp_loss), 2)
                }
            })

        self.alerts = new_alerts

    def _loop(self):
        print("[PingMonitor] Thread iniciada com sucesso.")
        while self.running:
            try:
                self._ping_all()
            except Exception as e:
                print(f"[PingMonitor] Erro no loop de monitoramento: {e}")
            time.sleep(self.interval)

    def start(self):
        with self.lock:
            if self.running and self.thread and self.thread.is_alive():
                print("[PingMonitor] Já está em execução (no-op).")
                return
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            print("[PingMonitor] Iniciado em segundo plano.")

    def stop(self):
        with self.lock:
            self.running = False
            if self.thread and self.thread.is_alive():
                if threading.current_thread() != self.thread:
                    self.thread.join(timeout=2)
                print("[PingMonitor] Parado.")

    def get_latest_data(self):
        with self.lock:
            data = {}
            for ip in self.targets:
                latest = self.history[ip][-1] if self.history[ip] else {"latency": 0.0, "loss": 0.0, "timestamp": ""}
                # Calcula a média dos pings de histórico
                history_slice = self.history[ip]
                avg_loss = sum(h["loss"] for h in history_slice) / len(history_slice) if history_slice else 0.0
                valid_latencies = [h["latency"] for h in history_slice if h["loss"] == 0.0]
                avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0.0
                
                data[ip] = {
                    "name": self.targets[ip],
                    "current_latency": latest["latency"],
                    "current_loss": latest["loss"],
                    "avg_latency": round(avg_latency, 2),
                    "avg_loss": round(avg_loss, 2),
                    "history": self.history[ip]
                }
            return {
                "devices": data,
                "alerts": self.alerts,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
