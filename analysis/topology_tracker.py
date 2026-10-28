import os
import json
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.db')
STATE_FILE = os.path.join(DB_DIR, 'topology_state.json')
CHANGES_FILE = os.path.join(DB_DIR, 'topology_changes.json')

class TopologyTracker:
    def __init__(self, netdisco_client, librenms_client=None):
        self.netdisco = netdisco_client
        self.librenms = librenms_client
        
        # Cria diretório de banco local se não existir
        os.makedirs(DB_DIR, exist_ok=True)

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return set(tuple(x) for x in json.load(f))
            except Exception:
                pass
        return set()

    def _save_state(self, state):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(list(list(x) for x in state), f, indent=2)
        except Exception:
            pass

    def load_changes_history(self):
        if os.path.exists(CHANGES_FILE):
            try:
                with open(CHANGES_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_change_event(self, event):
        history = self.load_changes_history()
        # Insere no início para mostrar os mais recentes primeiro
        history.insert(0, event)
        # Limita o histórico aos últimos 50 eventos
        history = history[:50]
        try:
            with open(CHANGES_FILE, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

    def check_topology_changes(self):
        """Compara a topologia atual com o estado salvo e registra alterações."""
        try:
            current_topology = self.netdisco.get_topology()
        except Exception as e:
            # Se não conseguir buscar a topologia, retorna o histórico existente
            return self.load_changes_history()

        # Reconstrói os links atuais como conjunto de tuplas ordenadas para evitar duplicidade bidirecional
        current_links = set()
        link_details = {} # Mapeamento para recuperar os nomes amigáveis depois
        
        for link in current_topology:
            dev_a = link.get("from_device")
            port_a = link.get("from_port")
            dev_b = link.get("to_device")
            port_b = link.get("to_port")
            
            if not all([dev_a, port_a, dev_b, port_b]):
                continue
                
            # Tupla ordenada do link físico
            link_tuple = tuple(sorted([f"{dev_a}:{port_a}", f"{dev_b}:{port_b}"]))
            current_links.add(link_tuple)
            
            # Armazena detalhes
            link_details[link_tuple] = {
                "dev_a": dev_a,
                "dev_a_name": link.get("from_device_name") or dev_a,
                "port_a": port_a,
                "dev_b": dev_b,
                "dev_b_name": link.get("to_device_name") or dev_b,
                "port_b": port_b
            }

        previous_links = self._load_state()

        # Se for a primeira execução e não tiver estado salvo, salva e não gera eventos
        if not previous_links:
            self._save_state(current_links)
            return self.load_changes_history()

        # Links removidos (estavam no estado anterior, mas sumiram)
        removed_links = previous_links.difference(current_links)
        # Links adicionados (novos)
        added_links = current_links.difference(previous_links)

        # Processa links removidos (cadas de conexões físicas)
        for link in removed_links:
            # Reconstrói os dados do link a partir da string ou usa o histórico
            parts_a, parts_b = link[0].split(':'), link[1].split(':')
            dev_a, port_a = parts_a[0], parts_a[1]
            dev_b, port_b = parts_b[0], parts_b[1]
            
            # Tenta descobrir quem disparou a queda do link
            trigger_device = "Indeterminado"
            trigger_details = "Ambos os lados parecem ativos ou indisponíveis para checagem."
            
            if self.librenms:
                try:
                    # Busca status das portas dos dois lados via LibreNMS
                    ports_a = self.librenms.get_device_ports(dev_a)
                    ports_b = self.librenms.get_device_ports(dev_b)
                    
                    status_a = next((p.get("ifOperStatus") for p in ports_a if p.get("ifName") == port_a or p.get("ifDescr") == port_a), None)
                    status_b = next((p.get("ifOperStatus") for p in ports_b if p.get("ifName") == port_b or p.get("ifDescr") == port_b), None)
                    
                    if status_a == "down" and status_b == "up":
                        trigger_device = dev_a
                        trigger_details = f"A porta {port_a} no dispositivo {dev_a} foi detectada como DOWN."
                    elif status_b == "down" and status_a == "up":
                        trigger_device = dev_b
                        trigger_details = f"A porta {port_b} no dispositivo {dev_b} foi detectada como DOWN."
                    elif status_a == "down" and status_b == "down":
                        trigger_device = "Ambos"
                        trigger_details = f"Portas em ambos os lados do link ({port_a} e {port_b}) estão DOWN."
                except Exception:
                    pass

            event = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event_type": "link_down",
                "severity": "critical",
                "device_a": dev_a,
                "port_a": port_a,
                "device_b": dev_b,
                "port_b": port_b,
                "trigger_device": trigger_device,
                "trigger_details": trigger_details,
                "description": f"O link físico entre {dev_a} ({port_a}) e {dev_b} ({port_b}) caiu."
            }
            self._save_change_event(event)

        # Processa links adicionados (novas conexões)
        for link in added_links:
            details = link_details.get(link)
            if details:
                dev_a = details["dev_a"]
                port_a = details["port_a"]
                dev_b = details["dev_b"]
                port_b = details["port_b"]
            else:
                parts_a, parts_b = link[0].split(':'), link[1].split(':')
                dev_a, port_a = parts_a[0], parts_a[1]
                dev_b, port_b = parts_b[0], parts_b[1]

            event = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event_type": "link_up",
                "severity": "info",
                "device_a": dev_a,
                "port_a": port_a,
                "device_b": dev_b,
                "port_b": port_b,
                "trigger_device": "Descoberta LLDP/CDP",
                "trigger_details": "Novo vizinho físico detectado.",
                "description": f"Nova conexão física estabelecida entre {dev_a} ({port_a}) e {dev_b} ({port_b})."
            }
            self._save_change_event(event)

        # Atualiza o estado salvo da topologia
        if removed_links or added_links:
            self._save_state(current_links)

        return self.load_changes_history()
