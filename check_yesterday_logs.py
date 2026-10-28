import sys
import os
import json
from datetime import datetime

PROJECT_DIR = "/Users/administrator/Desktop/Rossi/Desenvolvimento/Redes"
sys.path.append(PROJECT_DIR)

from clients.librenms import LibreNMSClient

def main():
    with open(os.path.join(PROJECT_DIR, 'config.json'), 'r') as f:
        config = json.load(f)
        
    librenms_cfg = config.get("librenms", {})
    verify_ssl = config.get("settings", {}).get("verify_ssl", False)
    
    # Inicializa o cliente do LibreNMS
    client = LibreNMSClient(
        url=librenms_cfg.get("url"),
        api_token=librenms_cfg.get("api_token"),
        verify_ssl=verify_ssl
    )
    
    # Vamos buscar os logs de ontem 2026-06-08 das 16:15:00 às 16:30:00
    start_time = "2026-06-08 16:20:00"
    end_time = "2026-06-08 16:22:00"
    
    print(f"Buscando syslogs no LibreNMS de {start_time} até {end_time}...")
    
    try:
        # Request syslog
        res = client._request("logs/syslog", params={"from": start_time, "limit": 1000})
        logs = res.get("logs", [])
        
        filtered_logs = []
        for l in logs:
            ts = l.get("timestamp")
            if start_time <= ts <= end_time:
                filtered_logs.append(l)
                
        print(f"Total de logs encontrados na janela: {len(filtered_logs)}")
        
        # Filtra e agrupa logs por switch ou tipo de evento
        for l in sorted(filtered_logs, key=lambda x: x.get("timestamp")):
            print(f"[{l.get('timestamp')}] {l.get('hostname')} ({l.get('sysName') or 'N/A'}): {l.get('msg')}")
            
    except Exception as e:
        print(f"Erro ao buscar logs do LibreNMS: {e}")

if __name__ == '__main__':
    main()
