#!/usr/bin/env python3
import sys
import os
import json
import argparse
import pexpect
import urllib3

# Desabilitar avisos de SSL se necessário
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de caminhos do projeto
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_DIR, 'config.json')

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def classify_device(dev):
    """
    Classifica o switch com base no modelo, nome ou fabricante obtidos do Netdisco.
    Retorna: 'dell', 'aruba', 'comware' ou 'unknown'.
    """
    model = str(dev.get("model", "")).lower()
    name = str(dev.get("name", "")).lower()
    vendor = str(dev.get("vendor", "") or dev.get("vendor_name", "") or "").lower()
    
    # Ruckus APs e linux/gateways devem ser ignorados
    if any(x in model for x in ["r700", "r710", "zf7055", "r310", "linux", "u7-pro"]):
        return "ignored"
        
    if "s4048" in model or "dell" in name or "dell" in vendor:
        return "dell"
    elif any(x in model for x in ["2910", "2930", "2920", "j9983", "aruba", "procurve", "hp_dc"]):
        return "aruba"
    elif any(x in model for x in ["v1910", "1920", "2928", "2952", "5120", "baseline", "3com", "comware", "h3c", "a5120"]):
        return "comware"
    
    # Se o nome tem SW ou SWITCH, e não for ignorado, tenta classificar por padrão
    if "sw" in name or "switch" in name:
        if "dell" in name:
            return "dell"
        elif "hp" in name or "aruba" in name:
            return "aruba"
        else:
            return "comware" # Comware é o padrão na rede se for outro switch
            
    return "unknown"

def generate_commands(vlan_id, description, os_type, ports):
    """
    Gera a lista de comandos CLI baseada no tipo de sistema operacional do switch.
    """
    commands = []
    
    if os_type == "dell":
        commands = [
            "configure terminal",
            f"interface Vlan {vlan_id}",
            f"description {description}",
            "no shutdown"
        ]
        for port in ports:
            commands.append(f"tagged {port}")
        commands.append("exit")
        commands.append("end")
        commands.append("write memory")
        
    elif os_type == "aruba":
        commands = [
            "configure terminal",
            f"vlan {vlan_id}",
            f"name \"{description}\""
        ]
        for port in ports:
            commands.append(f"tagged {port}")
        commands.append("exit")
        commands.append("end")
        commands.append("write memory")
        
    elif os_type == "comware":
        commands = [
            "system-view",
            f"vlan {vlan_id}",
            f"description {description}",
            "quit"
        ]
        for port in ports:
            # Em switches Comware, a porta trunk deve permitir a VLAN no contexto da interface
            commands.append(f"interface {port}")
            commands.append(f"port trunk permit vlan {vlan_id}")
            commands.append("quit")
        commands.append("quit") # Volta para o modo de visualização do usuário para salvar
        commands.append("save")
        
    return commands

def execute_on_switch(host, username, password, os_type, commands):
    """
    Executa os comandos CLI em um switch específico usando pexpect (SSH).
    """
    print(f"\n---> Conectando via SSH a {host} ({os_type.upper()})...")
    
    # Parâmetros SSH para compatibilidade com algoritmos legados (comum em switches mais antigos)
    ssh_cmd = (
        f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"-o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 "
        f"-o Ciphers=+aes128-cbc,aes256-cbc,3des-cbc "
        f"{username}@{host}"
    )
    
    try:
        child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=20)
        
        # Lida com o prompt de senha ou chave host
        idx = child.expect([r"(?i)password:", r"yes/no", pexpect.EOF, pexpect.TIMEOUT])
        if idx == 1:
            child.sendline("yes")
            child.expect(r"(?i)password:")
            child.sendline(password)
        elif idx == 0:
            child.sendline(password)
        else:
            print(f"  [ERRO] Falha ao iniciar SSH com {host}.")
            return False
            
        # Espera o prompt inicial (geralmente termina com > ou #)
        prompt_idx = child.expect([r"#", r">", r"\]"])
        
        # Envia os comandos um a um
        for cmd in commands:
            print(f"  Enviando comando: {cmd}")
            child.sendline(cmd)
            
            # Se for o comando 'save' do Comware, lida com as confirmações extras
            if cmd == "save" and os_type == "comware":
                save_idx = child.expect([r"\[Y/N\]", pexpect.TIMEOUT], timeout=5)
                if save_idx == 0:
                    child.sendline("Y")
                    # Pode pedir o nome do arquivo, ex: flash:/startup.cfg
                    file_idx = child.expect([r"\.cfg\]", pexpect.TIMEOUT], timeout=3)
                    if file_idx == 0:
                        child.sendline("") # Pressiona Enter
                    # Pode perguntar se deseja sobrescrever
                    overwrite_idx = child.expect([r"(?i)overwrite|\[Y/N\]", pexpect.TIMEOUT], timeout=3)
                    if overwrite_idx == 0:
                        child.sendline("Y")
            
            # Espera o próximo prompt
            child.expect([r"#", r">", r"\]", r"\(config.*\)#", r"\(conf-.*\)#"])
            
        child.sendline("exit")
        child.close()
        print(f"  [SUCESSO] Configurações aplicadas com sucesso em {host}!")
        return True
        
    except Exception as e:
        print(f"  [ERRO] Falha na execução em {host}: {e}")
        try:
            child.close()
        except:
            pass
        return False

def main():
    parser = argparse.ArgumentParser(description="Multi-vendor VLAN Replicator (Netdisco Integration)")
    parser.add_argument("vlan_id", type=int, help="ID da VLAN a ser criada (ex: 380)")
    parser.add_argument("description", type=str, help="Descrição/Nome da VLAN (ex: VLAN_PROD_D)")
    parser.add_argument("--execute", action="store_true", help="Executa as alterações nos switches (se omitido, roda em modo DRY-RUN)")
    parser.add_argument("--user", type=str, help="Usuário SSH dos switches (padrão do config ou alessandro.rossi)")
    parser.add_argument("--password", type=str, help="Senha SSH dos switches")
    parser.add_argument("--target-ip", type=str, help="Executa apenas no switch especificado por IP")
    
    args = parser.parse_args()
    
    # Carrega configurações globais
    config = load_config()
    netdisco_cfg = config.get("netdisco", {})
    verify_ssl = config.get("settings", {}).get("verify_ssl", False)
    
    switch_user = args.user or config.get("switches", {}).get("user") or ""
    switch_pass = args.password or config.get("switches", {}).get("password") or ""
    
    # Inicializa cliente Netdisco
    sys.path.append(PROJECT_DIR)
    from clients.netdisco import NetdiscoClient
    
    n_client = NetdiscoClient(
        url=netdisco_cfg.get("url"),
        user=netdisco_cfg.get("user"),
        password=netdisco_cfg.get("password"),
        api_token=netdisco_cfg.get("api_token"),
        verify_ssl=verify_ssl
    )
    
    print("Conectando na API do Netdisco para carregar inventário...")
    try:
        n_client.login()
        devices = n_client.get_devices()
        topology = n_client.get_topology()
    except Exception as e:
        print(f"[ERRO] Falha ao consultar Netdisco: {e}")
        sys.exit(1)
        
    print(f"Total de dispositivos descobertos no Netdisco: {len(devices)}")
    print(f"Total de conexões físicas na topologia: {len(topology)}")
    
    # Mapeia as conexões físicas (uplinks) de cada dispositivo
    # Isso nos ajuda a saber em quais portas de cada switch devemos taggear a VLAN de trânsito
    device_uplinks = {}
    for link in topology:
        dev_a = link.get("from_device")
        port_a = link.get("from_port")
        dev_b = link.get("to_device")
        port_b = link.get("to_port")
        
        if dev_a and port_a:
            if dev_a not in device_uplinks:
                device_uplinks[dev_a] = set()
            device_uplinks[dev_a].add(port_a)
            
        if dev_b and port_b:
            if dev_b not in device_uplinks:
                device_uplinks[dev_b] = set()
            device_uplinks[dev_b].add(port_b)
            
    # Classifica e filtra os dispositivos que são switches de rede
    switches_to_configure = []
    
    for dev in devices:
        ip = dev.get("ip")
        name = dev.get("name", ip)
        
        if args.target_ip and ip != args.target_ip:
            continue
            
        os_type = classify_device(dev)
        if os_type == "ignored" or os_type == "unknown":
            continue
            
        # Pega as portas de uplink detectadas para este dispositivo
        ports = sorted(list(device_uplinks.get(ip, [])))
        
        # Caso especial para os switches Dell informados pelo usuário:
        # Se não houver topologia mapeada, garante que a porta de interconexão padrão está incluída
        if not ports and ip in ["10.11.0.248", "10.11.0.249", "10.11.0.251", "172.16.11.248", "172.16.11.249"]:
            ports = ["Port-channel 49"]
            
        switches_to_configure.append({
            "ip": ip,
            "name": name,
            "os_type": os_type,
            "ports": ports,
            "model": dev.get("model", "N/A")
        })
        
    print(f"\nSwitches mapeados para replicação de VLAN ({len(switches_to_configure)} switches):")
    for sw in switches_to_configure:
        print(f" - {sw['name']} ({sw['ip']}) | Modelo: {sw['model']} | OS: {sw['os_type'].upper()} | Portas Uplink: {', '.join(sw['ports']) or 'Nenhuma detectada'}")
        
    print("\n--------------------------------------------------")
    print(f"GERANDO COMANDOS CLI PARA VLAN {args.vlan_id} ({args.description})")
    print("--------------------------------------------------")
    
    for sw in switches_to_configure:
        cmds = generate_commands(args.vlan_id, args.description, sw["os_type"], sw["ports"])
        print(f"\n[Switch: {sw['name']} ({sw['ip']}) - {sw['os_type'].upper()}]")
        for cmd in cmds:
            print(f"  {cmd}")
            
    print("\n==================================================")
    if not args.execute:
        print("MODO DRY-RUN (SIMULAÇÃO): Nenhum comando foi enviado aos switches reais.")
        print("Para aplicar essas configurações em todos os switches da rede, execute o script com o parâmetro --execute:")
        print(f"  python3 vlan_replicator.py {args.vlan_id} \"{args.description}\" --execute")
        print("==================================================")
    else:
        print("MODO EXECUÇÃO ATIVO: As alterações serão enviadas via SSH.")
        print("Atenção! Pressione CTRL+C agora para abortar ou aguarde 5 segundos para iniciar...")
        print("==================================================")
        import time
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nExecução cancelada pelo usuário.")
            sys.exit(0)
            
        success_count = 0
        for sw in switches_to_configure:
            cmds = generate_commands(args.vlan_id, args.description, sw["os_type"], sw["ports"])
            ok = execute_on_switch(sw["ip"], switch_user, switch_pass, sw["os_type"], cmds)
            if ok:
                success_count += 1
                
        print(f"\nReplicação finalizada: {success_count} de {len(switches_to_configure)} switches configurados com sucesso.")

if __name__ == "__main__":
    main()
