import requests
from typing import Dict, Any, List, Optional
from app.models.provision_dependency import DependencyStatus, DependencyResult, CanonicalHostIdentity

class ProvisionDependencyEngine:
    """
    Dependency Engine: Performs 100% read-only pre-discovery across NetBox, Zabbix, LibreNMS, and NetDisco.
    STRICT RULE: NO WRITE OPERATIONS ALLOWED DURING DISCOVERY.
    """

    @staticmethod
    def discover_all(canonical: CanonicalHostIdentity, config: Dict[str, Any]) -> Dict[str, DependencyResult]:
        requests.packages.urllib3.disable_warnings()

        nb_res = ProvisionDependencyEngine.discover_netbox(canonical, config)
        zb_res = ProvisionDependencyEngine.discover_zabbix(canonical, config)
        lnms_res = ProvisionDependencyEngine.discover_librenms(canonical, config)
        nd_res = ProvisionDependencyEngine.discover_netdisco(canonical, config)

        return {
            "netbox": nb_res,
            "zabbix": zb_res,
            "librenms": lnms_res,
            "netdisco": nd_res
        }

    @staticmethod
    def discover_netbox(canonical: CanonicalHostIdentity, config: Dict[str, Any]) -> DependencyResult:
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json", "Accept": "application/json"}

        conflicts = []
        try:
            # 1. Check Device / VM existence
            d_res = requests.get(f"{base_url}/api/dcim/devices/?name={canonical.hostname}", headers=headers, verify=False, timeout=3)
            existing_id = None
            device_found = False

            if d_res.status_code == 200 and d_res.json().get('count', 0) > 0:
                device_found = True
                existing_id = d_res.json()['results'][0]['id']
            else:
                vm_res = requests.get(f"{base_url}/api/virtualization/virtual-machines/?name={canonical.hostname}", headers=headers, verify=False, timeout=3)
                if vm_res.status_code == 200 and vm_res.json().get('count', 0) > 0:
                    device_found = True
                    existing_id = vm_res.json()['results'][0]['id']

            # 2. Check IP Address assignment & conflict
            ip_res = requests.get(f"{base_url}/api/ipam/ip-addresses/?address={canonical.ip}", headers=headers, verify=False, timeout=3)
            if ip_res.status_code == 200 and ip_res.json().get('count', 0) > 0:
                ip_obj = ip_res.json()['results'][0]
                assigned_obj = ip_obj.get('assigned_object')
                if assigned_obj and not device_found:
                    conflicts.append(f"O IP {canonical.ip} no NetBox já está atribuído a outro dispositivo (ID: {assigned_obj.get('id')}).")

            if conflicts:
                return DependencyResult(
                    system="NetBox",
                    object_type="device/ip",
                    requested_identifier=canonical.hostname,
                    status=DependencyStatus.CONFLICT,
                    conflicts=conflicts
                )

            if device_found:
                return DependencyResult(
                    system="NetBox",
                    object_type="device",
                    requested_identifier=canonical.hostname,
                    status=DependencyStatus.EXISTING,
                    object_id=existing_id
                )

            return DependencyResult(
                system="NetBox",
                object_type="device",
                requested_identifier=canonical.hostname,
                status=DependencyStatus.ABSENT
            )

        except Exception as e:
            return DependencyResult(
                system="NetBox",
                object_type="device",
                requested_identifier=canonical.hostname,
                status=DependencyStatus.UNKNOWN,
                conflicts=[f"Erro de comunicação com NetBox: {str(e)}"]
            )

    @staticmethod
    def discover_zabbix(canonical: CanonicalHostIdentity, config: Dict[str, Any]) -> DependencyResult:
        zabbix_cfg = config.get('zabbix', {})
        zabbix_url = zabbix_cfg.get('url', '').rstrip('/')
        user_zb = zabbix_cfg.get('user', 'Admin')
        pwd_zb = zabbix_cfg.get('password', '')

        conflicts = []
        try:
            auth_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {"username": user_zb, "password": pwd_zb},
                "id": 1
            }, timeout=3).json()

            token = auth_res.get('result') if isinstance(auth_res, dict) else None

            if not token:
                return DependencyResult(system="Zabbix", object_type="host", requested_identifier=canonical.hostname, status=DependencyStatus.UNKNOWN, conflicts=["Falha na autenticação Zabbix"])

            # Search by Hostname
            h_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                "jsonrpc": "2.0",
                "method": "host.get",
                "params": {"filter": {"host": [canonical.hostname]}, "selectInterfaces": ["ip"]},
                "auth": token,
                "id": 2
            }, timeout=3).json()

            if isinstance(h_res, dict) and isinstance(h_res.get('result'), list) and len(h_res['result']) > 0:
                host_obj = h_res['result'][0]
                if isinstance(host_obj, dict):
                    host_id = host_obj.get('hostid')
                    interfaces = host_obj.get('interfaces', [])
                    existing_ip = interfaces[0].get('ip') if (interfaces and isinstance(interfaces[0], dict)) else None

                    if existing_ip and existing_ip != canonical.ip:
                        conflicts.append(f"Zabbix host '{canonical.hostname}' já existe mas aponta para o IP {existing_ip} (esperado: {canonical.ip}).")
                        return DependencyResult(
                            system="Zabbix",
                            object_type="host",
                            requested_identifier=canonical.hostname,
                            status=DependencyStatus.CONFLICT,
                            object_id=host_id,
                            conflicts=conflicts
                        )

                    return DependencyResult(
                        system="Zabbix",
                        object_type="host",
                        requested_identifier=canonical.hostname,
                        status=DependencyStatus.EXISTING,
                        object_id=host_id
                    )

            return DependencyResult(
                system="Zabbix",
                object_type="host",
                requested_identifier=canonical.hostname,
                status=DependencyStatus.ABSENT
            )

        except Exception as e:
            return DependencyResult(
                system="Zabbix",
                object_type="host",
                requested_identifier=canonical.hostname,
                status=DependencyStatus.UNKNOWN,
                conflicts=[f"Erro Zabbix: {str(e)}"]
            )

    @staticmethod
    def discover_librenms(canonical: CanonicalHostIdentity, config: Dict[str, Any]) -> DependencyResult:
        lnms_cfg = config.get('librenms', {})
        lnms_url = lnms_cfg.get('url', '').rstrip('/')
        lnms_token = lnms_cfg.get('api_token', '')
        headers = {"X-Auth-Token": lnms_token, "Content-Type": "application/json"}

        try:
            res = requests.get(f"{lnms_url}/api/v0/devices/{canonical.ip}", headers=headers, timeout=3)
            if res.status_code == 200:
                dev = res.json().get('devices', [{}])[0]
                return DependencyResult(
                    system="LibreNMS",
                    object_type="device",
                    requested_identifier=canonical.ip,
                    status=DependencyStatus.EXISTING,
                    object_id=dev.get('device_id')
                )
            return DependencyResult(
                system="LibreNMS",
                object_type="device",
                requested_identifier=canonical.ip,
                status=DependencyStatus.ABSENT
            )
        except Exception:
            return DependencyResult(
                system="LibreNMS",
                object_type="device",
                requested_identifier=canonical.ip,
                status=DependencyStatus.ABSENT
            )

    @staticmethod
    def discover_netdisco(canonical: CanonicalHostIdentity, config: Dict[str, Any]) -> DependencyResult:
        netdisco_cfg = config.get('netdisco', {})
        netdisco_url = netdisco_cfg.get('url', '').rstrip('/')
        try:
            res = requests.get(f"{netdisco_url}/api/v1/object/device/{canonical.ip}", timeout=3)
            if res.status_code == 200:
                return DependencyResult(
                    system="NetDisco",
                    object_type="device",
                    requested_identifier=canonical.ip,
                    status=DependencyStatus.EXISTING,
                    object_id=canonical.ip
                )
            return DependencyResult(
                system="NetDisco",
                object_type="device",
                requested_identifier=canonical.ip,
                status=DependencyStatus.ABSENT
            )
        except Exception:
            return DependencyResult(
                system="NetDisco",
                object_type="device",
                requested_identifier=canonical.ip,
                status=DependencyStatus.ABSENT
            )

    @staticmethod
    def build_dependency_dag(canonical: CanonicalHostIdentity) -> List[Dict[str, Any]]:
        """Build explicit DAG dependency graph."""
        return [
            {
                "operation_id": f"PROV-{canonical.hostname}-NB-DEVICE",
                "system": "NetBox",
                "action": "CREATE",
                "resource": "device",
                "depends_on": []
            },
            {
                "operation_id": f"PROV-{canonical.hostname}-NB-IP",
                "system": "NetBox",
                "action": "CREATE",
                "resource": "ip",
                "depends_on": [f"PROV-{canonical.hostname}-NB-DEVICE"]
            },
            {
                "operation_id": f"PROV-{canonical.hostname}-ZABBIX",
                "system": "Zabbix",
                "action": "CREATE",
                "resource": "host",
                "depends_on": [f"PROV-{canonical.hostname}-NB-IP"]
            },
            {
                "operation_id": f"PROV-{canonical.hostname}-LIBRENMS",
                "system": "LibreNMS",
                "action": "CREATE",
                "resource": "device",
                "depends_on": [f"PROV-{canonical.hostname}-NB-IP"]
            },
            {
                "operation_id": f"PROV-{canonical.hostname}-NETDISCO",
                "system": "NetDisco",
                "action": "DISCOVERY",
                "resource": "topology",
                "depends_on": [f"PROV-{canonical.hostname}-ZABBIX", f"PROV-{canonical.hostname}-LIBRENMS"]
            }
        ]
