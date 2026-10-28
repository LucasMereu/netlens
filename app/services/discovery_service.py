from typing import Dict, Any, List, Optional
from app.models.device import DeviceIdentity
from app.models.state_models import ObservedState
from app.drivers.factory import NetworkDriverFactory
from app.drivers.errors import ValidationError

class ReadOnlyDiscoveryDriverProxy:
    """
    Defesa em profundidade: Proxy que envolve o driver original e expoem apenas 
    metodos de leitura, bloqueando qualquer tentativa de modificacao.
    """
    def __init__(self, driver):
        self._driver = driver

    def __getattr__(self, name):
        # Permite apenas metodos que comecam com 'get_' ou 'validate_' ou connect/disconnect
        if name.startswith("get_") or name.startswith("validate_") or name in ("connect", "disconnect", "identity", "capabilities"):
            return getattr(self._driver, name)
        raise ValidationError(f"Acesso NEGADO: Tentativa de invocar operacao mutativa '{name}' a partir do DiscoveryService.")

class DiscoveryService:
    @staticmethod
    def discover_device(identity: DeviceIdentity) -> ObservedState:
        real_driver = NetworkDriverFactory.get_driver(identity)
        # Wrap driver with Read-Only proxy
        driver = ReadOnlyDiscoveryDriverProxy(real_driver)
        
        try:
            driver.connect()
            info = driver.get_device_info()
            
            # Map VLANs
            raw_vlans = driver.get_vlans()
            vlans = [{"vlan_id": v["vlan_id"], "name": v["name"]} for v in raw_vlans]
            
            # Map Interfaces
            raw_ifs = driver.get_interfaces()
            interfaces = []
            for i in raw_ifs:
                interfaces.append({
                    "name": i.name,
                    "admin_status": i.admin_status,
                    "oper_status": i.oper_status,
                    "mode": i.mode,
                    "native_vlan": i.native_vlan
                })
                
            # Map Trunks
            raw_trunks = driver.get_trunks()
            trunks = []
            for t in raw_trunks:
                trunks.append({
                    "name": t.get("name"),
                    "mode": t.get("mode"),
                    "native_vlan": t.get("native_vlan"),
                    "allowed_vlans": t.get("allowed_vlans", [])
                })
                
            # Map Neighbors
            neighbors = driver.get_neighbors()
            
            # Map STP
            stp = driver.get_stp_state()
            
            # Revision
            rev = driver.get_running_config_hash()
            
            return ObservedState(info, interfaces, vlans, trunks, neighbors, stp, rev)
            
        finally:
            try:
                driver.disconnect()
            except:
                pass

    @staticmethod
    def cross_check_topology(observed: ObservedState, netdisco_connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        
        # If dictionary received (like from test case neighbors wrapper), extract neighbors list
        if isinstance(netdisco_connections, dict):
            neighbors = netdisco_connections.get("neighbors", [])
            netdisco_list = []
            for n in neighbors:
                netdisco_list.append({
                    "from_port": n.get("local_interface"),
                    "to_device_name": n.get("remote_hostname"),
                    "to_port": n.get("remote_interface")
                })
            netdisco_connections = netdisco_list
            
        # We compare observed remote LLDP neighbors on this device with Netdisco links
        for obs_neigh in observed.neighbors:
            local_if = obs_neigh.get("local_interface")
            rem_host = obs_neigh.get("remote_hostname")
            rem_if = obs_neigh.get("remote_interface")
            
            # Look for link in Netdisco connections
            match_found = False
            for conn in netdisco_connections:
                # check both directions
                if conn.get("from_port") == local_if:
                    match_found = True
                    if conn.get("to_device_name") != rem_host:
                        results.append({
                            "local_interface": local_if,
                            "type": "HOSTNAME_MISMATCH",
                            "status": "HOSTNAME_MISMATCH",
                            "message": f"Divergencia de hostname: Netdisco relata '{conn.get('to_device_name')}', Switch real relata '{rem_host}'."
                        })
                    elif conn.get("to_port") != rem_if:
                        results.append({
                            "local_interface": local_if,
                            "type": "INTERFACE_MISMATCH",
                            "status": "INTERFACE_MISMATCH",
                            "message": f"Divergencia de porta remota: Netdisco relata '{conn.get('to_port')}', Switch real relata '{rem_if}'."
                        })
                    else:
                        results.append({
                            "local_interface": local_if,
                            "type": "MATCH",
                            "status": "MATCH",
                            "message": f"Topologia alinhada com Netdisco no link para {rem_host}."
                        })
                        
            if not match_found:
                results.append({
                    "local_interface": local_if,
                    "type": "MISSING_IN_NETDISCO",
                    "message": f"Conexao com {rem_host} na interface {local_if} ausente no Netdisco."
                })
                
        # Now find if Netdisco relata links which do NOT exist on the device neighbors list
        for conn in netdisco_connections:
            local_if = conn.get("from_port")
            obs_neigh = next((n for n in observed.neighbors if n.get("local_interface") == local_if), None)
            if not obs_neigh:
                results.append({
                    "local_interface": local_if,
                    "type": "MISSING_ON_DEVICE",
                    "message": f"Netdisco relata conexao na interface {local_if}, mas nenhum vizinho LLDP foi encontrado no equipamento."
                })
                
        return results
