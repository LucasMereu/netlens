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
            self.targets = {
                "10.11.0.249": "Dell Fibra Gerência (Mgmt)",
                "10.1.1.1": "Dell Fibra Point-to-Point (SVI)",
                "10.1.1.2": "Sophos Firewall (Data Plane)",
                "10.11.0.248": "Dell Fibra Ethernet Física (Mgmt Eth)"
            }
        else:
            self.targets = targets

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
            # Dell Mgmt (10.11.0.249) e Dell SVI (10.1.1.1) caem (100% loss)
            # Sophos e Dell Mgmt Eth funcionam normalmente
            cycle = self.sim_tick % 20
            is_failing = (8 <= cycle < 12)
            
            import random
            if is_failing and ip in ["10.11.0.249", "10.1.1.1"]:
                return 0.0, 100.0
            
            if ip == "10.11.0.249":
                return round(random.uniform(0.4, 1.2), 2), 0.0
            elif ip == "10.1.1.1":
                return round(random.uniform(0.3, 2.5), 2), 0.0
            elif ip == "10.1.1.2":
                return round(random.uniform(0.2, 0.6), 2), 0.0
            else:  # 10.11.0.248
                return round(random.uniform(0.4, 0.8), 2), 0.0

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

        # Regra de Correlação:
        # Se Dell Fibra Gerência (10.11.0.249) e Dell Fibra PtP (10.1.1.1)
        # tiverem perda significativa (>20%), mas Sophos (10.1.1.2) e Dell Mgmt Eth (10.11.0.248)
        # estiverem operando normalmente (perda < 10%).
        dell_mgmt_loss = loss_stats.get("10.11.0.249", 0.0)
        dell_ptp_loss = loss_stats.get("10.1.1.1", 0.0)
        sophos_loss = loss_stats.get("10.1.1.2", 0.0)
        dell_eth_loss = loss_stats.get("10.11.0.248", 0.0)

        # Também verifica se o último ping falhou para resposta rápida
        last_dell_mgmt = self.history["10.11.0.249"][-1] if self.history["10.11.0.249"] else {"loss": 0.0}
        last_dell_ptp = self.history["10.1.1.1"][-1] if self.history["10.1.1.1"] else {"loss": 0.0}

        is_intermittent = (
            (dell_mgmt_loss >= 20.0 or last_dell_mgmt["loss"] == 100.0) and
            (dell_ptp_loss >= 20.0 or last_dell_ptp["loss"] == 100.0) and
            (sophos_loss < 20.0) and
            (dell_eth_loss < 20.0)
        )

        new_alerts = []
        if is_intermittent:
            # Calcula latência média para os que estão funcionando
            sophos_lat = f"{latency_stats.get('10.1.1.2', 0.0):.2f} ms"
            dell_eth_lat = f"{latency_stats.get('10.11.0.248', 0.0):.2f} ms"
            
            new_alerts.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "severity": "critical",
                "alert_type": "dell_control_plane_intermittency",
                "title": "Intermitência no Plano de Controle do Switch Dell (CPU)",
                "description": (
                    "Detectada perda de pacotes e alta latência nos IPs de gerência virtual (10.11.0.249) "
                    "e interface Ponto a Ponto (10.1.1.1). No entanto, o tráfego de trânsito (data plane) "
                    f"para o Sophos Firewall (10.1.1.2) está normal ({sophos_lat}) e a gerência "
                    f"via cabo físico Ethernet (10.11.0.248) também está operando normalmente ({dell_eth_lat}). "
                    "Isso indica congestionamento, pico de CPU ou instabilidade no Plano de Controle do Dell Fibra, "
                    "sem afetar o tráfego de dados passante."
                ),
                "metrics": {
                    "dell_mgmt_loss": dell_mgmt_loss,
                    "dell_ptp_loss": dell_ptp_loss,
                    "sophos_loss": sophos_loss,
                    "dell_eth_loss": dell_eth_loss
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
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            print("[PingMonitor] Iniciado em segundo plano.")

    def stop(self):
        self.running = False
        if self.thread:
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
