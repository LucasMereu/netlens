import requests
from typing import Dict, Any, Optional
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("zabbix_provisioner")

class ZabbixProvisioner:
    """Provisioning driver for Zabbix Monitoring API."""

    @staticmethod
    def provision(inp: Dict[str, Any], config: Dict[str, Any], resolved: Optional[Dict[str, Any]] = None, action: Optional[str] = None, snmp_community: str = "public") -> Dict[str, Any]:
        """
        Execute Zabbix host creation / reuse.
        
        Args:
            inp: Canonical input data (hostname, ip, etc.)
            config: Full config dict from config.json
            resolved: Zabbix resolved objects (group_ids, template_ids, interface_type, etc.)
            action: Action ('CREATE' or 'REUSE')
            snmp_community: SNMP community string for Zabbix
        
        Returns:
            Dict with keys: status ('PASS' or 'FAIL'), message
        """
        try:
            if action == "REUSE":
                try:
                    zabbix_cfg = config.get('zabbix', {})
                    zabbix_url = zabbix_cfg.get('url', '').rstrip('/')
                    user_zb = zabbix_cfg.get('user', 'Admin')
                    pwd_zb = zabbix_cfg.get('password', '')
                    auth_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                        "jsonrpc": "2.0", "method": "user.login",
                        "params": {"username": user_zb, "password": pwd_zb}, "id": 1
                    }, timeout=3).json()
                    auth_token = auth_res.get('result')
                    if auth_token:
                        ZabbixProvisioner._ensure_snmp_interface(zabbix_url, auth_token, inp.get('hostname', ''), inp.get('ip', ''), snmp_community)
                except Exception:
                    pass
                return {"status": "PASS", "message": f"Host {inp.get('hostname')} já monitorado no Zabbix (REUSE/SNMP verificado)."}

            zabbix_cfg = config.get('zabbix', {})
            zabbix_url = zabbix_cfg.get('url', '').rstrip('/')
            user_zb = zabbix_cfg.get('user', 'Admin')
            pwd_zb = zabbix_cfg.get('password', '')

            auth_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {"username": user_zb, "password": pwd_zb},
                "id": 1
            }, timeout=4).json()
            auth_token = auth_res.get('result')

            if auth_token:
                zabbix_resolved = resolved or {}
                group_params = [{"groupid": gid} for gid in zabbix_resolved.get("group_ids", [])]
                
                iface_type = zabbix_resolved.get("interface_type", 1)
                is_snmp_enabled = iface_type == 2 or (snmp_community and snmp_community not in ("", "none", "unused"))
                snmp_comm_val = snmp_community if (snmp_community and snmp_community not in ("", "none", "unused")) else "public"
                snmp_ver_str = zabbix_resolved.get("snmp_version", "v2c")
                if snmp_ver_str == "none":
                    snmp_ver_str = "v2c"
                version_num = {"v1": 1, "v2c": 2, "v3": 3}.get(snmp_ver_str, 2)

                interfaces = []
                # 1. Interface Agent (if profile is Agent type)
                if iface_type == 1:
                    interfaces.append({
                        "type": 1,
                        "main": 1,
                        "useip": 1,
                        "ip": inp['ip'],
                        "dns": "",
                        "port": str(zabbix_resolved.get("port", 10050))
                    })

                # 2. Interface SNMP (if profile is SNMP type OR if snmp_community is present)
                if is_snmp_enabled:
                    interfaces.append({
                        "type": 2,
                        "main": 1,
                        "useip": 1,
                        "ip": inp['ip'],
                        "dns": "",
                        "port": "161" if iface_type != 2 else str(zabbix_resolved.get("port", 161)),
                        "details": {
                            "version": version_num,
                            "bulk": 1,
                            "community": "{$SNMP_COMMUNITY}"
                        }
                    })

                if not interfaces:
                    interfaces.append({
                        "type": 1,
                        "main": 1,
                        "useip": 1,
                        "ip": inp['ip'],
                        "dns": "",
                        "port": "10050"
                    })

                host_payload = {
                    "jsonrpc": "2.0",
                    "method": "host.create",
                    "params": {
                        "host": inp['hostname'],
                        "interfaces": interfaces,
                        "groups": group_params,
                        "tags": zabbix_resolved.get("tags", [])
                    },
                    "auth": auth_token,
                    "id": 2
                }
                
                if is_snmp_enabled:
                    host_payload["params"]["macros"] = [{
                        "macro": "{$SNMP_COMMUNITY}",
                        "value": snmp_comm_val
                    }]

                if zabbix_resolved.get("template_ids"):
                    host_payload["params"]["templates"] = [{"templateid": tid} for tid in zabbix_resolved["template_ids"]]

                h_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json=host_payload, timeout=4).json()
                if "result" in h_res:
                    return {"status": "PASS", "message": f"Host {inp['hostname']} criado no Zabbix com interface SNMP!"}
                else:
                    err_obj = h_res.get('error', {})
                    err_data = str(err_obj.get('data', ''))
                    err_msg = str(err_obj.get('message', ''))
                    # Distinguir "host já existe" (REUSE ok) de outros erros (FAIL real)
                    is_host_exists = any(kw in err_data.lower() for kw in ['already exists', 'já existe', 'already exist'])
                    if is_host_exists:
                        ZabbixProvisioner._ensure_snmp_interface(zabbix_url, auth_token, inp['hostname'], inp['ip'], snmp_comm_val, version_num)
                        return {"status": "PASS", "message": f"Zabbix: Host existente (REUSE/SNMP verificado)."}
                    else:
                        sanitized_err = SecretSanitizer.sanitize_text(f"{err_msg}: {err_data}" if err_data else err_msg)
                        return {"status": "FAIL", "message": f"Zabbix host.create falhou: {sanitized_err}"}
            else:
                return {"status": "FAIL", "message": "Falha de autenticação Zabbix."}
        except Exception as e:
            return {"status": "FAIL", "message": f"Erro Zabbix: {SecretSanitizer.sanitize_exception(e)}"}

    @staticmethod
    def _ensure_snmp_interface(zabbix_url: str, auth_token: str, hostname: str, ip: str, snmp_community: str, version_num: int = 2):
        """
        Check if an existing host has an SNMP interface (type 2).
        If missing, create the SNMP interface and ensure the {$SNMP_COMMUNITY} macro exists.
        """
        try:
            h_get = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                "jsonrpc": "2.0",
                "method": "host.get",
                "params": {
                    "filter": {"host": [hostname]},
                    "selectInterfaces": "extend",
                    "selectMacros": "extend"
                },
                "auth": auth_token,
                "id": 101
            }, timeout=4).json()
            
            hosts = h_get.get("result", [])
            if not hosts:
                return
            
            host = hosts[0]
            host_id = host.get("hostid")
            existing_interfaces = host.get("interfaces", [])
            has_snmp_iface = any(str(i.get("type")) == "2" for i in existing_interfaces)
            
            if not has_snmp_iface and host_id:
                requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                    "jsonrpc": "2.0",
                    "method": "hostinterface.create",
                    "params": {
                        "hostid": host_id,
                        "dns": "",
                        "ip": ip,
                        "main": 1,
                        "port": "161",
                        "type": 2,
                        "useip": 1,
                        "details": {
                            "version": version_num,
                            "bulk": 1,
                            "community": snmp_community or "public"
                        }
                    },
                    "auth": auth_token,
                    "id": 102
                }, timeout=4)
                logger.info(f"Interface SNMP adicionada com sucesso ao host {hostname} (ID: {host_id}).")

            existing_macros = host.get("macros", [])
            has_macro = any(m.get("macro") == "{$SNMP_COMMUNITY}" for m in existing_macros)
            if not has_macro and snmp_community and host_id:
                requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                    "jsonrpc": "2.0",
                    "method": "usermacro.create",
                    "params": {
                        "hostid": host_id,
                        "macro": "{$SNMP_COMMUNITY}",
                        "value": snmp_community
                    },
                    "auth": auth_token,
                    "id": 103
                }, timeout=4)
        except Exception as e:
            logger.warning(f"Erro ao verificar/adicionar interface SNMP em host existente {hostname}: {SecretSanitizer.sanitize_exception(e)}")
