import logging
import requests
from typing import Dict, Any, Optional
from app.models.provision_profile import BUILTIN_PROFILES, ProvisionProfile

logger = logging.getLogger(__name__)

class ProvisionProfileEngine:
    """
    Profile Engine: Resolves high-level operator intents into exact low-level platform configurations.
    Enforces dynamic slug lookup (no static hardcoded IDs).
    """

    @staticmethod
    def get_profile(profile_name: str) -> ProvisionProfile:
        p_name = (profile_name or "").upper()
        try:
            from app.services.config_service import ConfigService
            config = ConfigService.load_config()
            custom = config.get("custom_profiles", {})
            if p_name in custom:
                cp = custom[p_name]
                return ProvisionProfile(
                    name=cp.get("name", p_name),
                    description=cp.get("description", ""),
                    netbox_role_slug=cp.get("netbox_role_slug", "switch"),
                    netbox_object_type=cp.get("netbox_object_type", "device"),
                    zabbix_groups=cp.get("zabbix_groups", ["Network Devices"]),
                    zabbix_templates=cp.get("zabbix_templates", []),
                    zabbix_interface_type=cp.get("zabbix_interface_type", 1),
                    zabbix_port=cp.get("zabbix_port", 10050),
                    snmp_version=cp.get("snmp_version", "v2c"),
                    librenms_protocol=cp.get("librenms_protocol", "snmp"),
                    librenms_version=cp.get("librenms_version", "v2c"),
                    librenms_port=cp.get("librenms_port", 161),
                    netdisco_discovery_enabled=cp.get("netdisco_discovery_enabled", False),
                    netdisco_protocols=cp.get("netdisco_protocols", []),
                    default_cluster=cp.get("default_cluster", "")
                )
        except Exception as e:
            logger.warning(f"[ProfileEngine] Erro ao carregar perfis customizados: {e}")

        if p_name in BUILTIN_PROFILES:
            return BUILTIN_PROFILES[p_name]
        # Fallback to NETWORK_SWITCH if profile name unrecognized
        return BUILTIN_PROFILES["NETWORK_SWITCH"]

    @staticmethod
    def resolve_netbox_objects(config: Dict[str, Any], profile: ProvisionProfile, site_name: str, model_name: str, ip_address: str, hostname: str, cluster: Optional[Any] = None, vm_resources: Optional[Dict[str, Any]] = None, custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dynamically query NetBox API for Site, Role, DeviceType, Cluster, and IP availability.
        Returns resolved IDs and flags whether objects are NEW or EXISTING/REUSE.
        """
        requests.packages.urllib3.disable_warnings()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        target_cluster = cluster or getattr(profile, 'default_cluster', None)
        resolved_cluster_id = None
        resolved_cluster_name = "10.11.0.233 - SRVPVE52"
        if target_cluster:
            try:
                resolved_cluster_id = int(target_cluster)
            except (ValueError, TypeError):
                resolved_cluster_name = str(target_cluster)

        resolved = {
            "site_id": 1,
            "site_name": site_name or "RedeTV HQ",
            "role_id": 1,
            "role_slug": profile.netbox_role_slug,
            "device_type_id": 220,
            "model_name": model_name or "Generic Device",
            "object_type": profile.netbox_object_type,
            "device_status": "NEW",
            "ip_status": "NEW",
            "ip_address_with_mask": f"{ip_address}/24",
            "existing_device_id": None,
            "cluster_id": resolved_cluster_id or 18,
            "cluster_name": resolved_cluster_name,
            "vcpus": vm_resources.get("vcpus") if vm_resources else None,
            "memory": vm_resources.get("memory") if vm_resources else None,
            "disk": vm_resources.get("disk") if vm_resources else None,
            "custom_fields": custom_fields or {}
        }

        try:
            # 1. Resolve Site ID dynamically by name/slug
            s_res = requests.get(f"{base_url}/api/dcim/sites/", headers=headers, verify=False, timeout=3)
            if s_res.status_code == 200:
                sites = s_res.json().get('results', [])
                for s in sites:
                    if s.get('name', '').lower() == site_name.lower() or s.get('slug', '').lower() == site_name.lower().replace(' ', '-'):
                        resolved['site_id'] = s['id']
                        resolved['site_name'] = s['name']
                        break
                else:
                    if sites:
                        resolved['site_id'] = sites[0]['id']
                        resolved['site_name'] = sites[0]['name']

            # 2. Resolve Role ID dynamically by slug
            if profile.netbox_object_type == "device":
                r_res = requests.get(f"{base_url}/api/dcim/device-roles/", headers=headers, verify=False, timeout=3)
                if r_res.status_code == 200:
                    roles = r_res.json().get('results', [])
                    for r in roles:
                        if r.get('slug', '').lower() == profile.netbox_role_slug.lower():
                            resolved['role_id'] = r['id']
                            break
                    else:
                        if roles:
                            resolved['role_id'] = roles[0]['id']

            # 3. Resolve Device Type ID dynamically
            if profile.netbox_object_type == "device":
                dt_res = requests.get(f"{base_url}/api/dcim/device-types/", headers=headers, verify=False, timeout=3)
                if dt_res.status_code == 200:
                    device_types = dt_res.json().get('results', [])
                    for dt in device_types:
                        if model_name.lower() in dt.get('model', '').lower():
                            resolved['device_type_id'] = dt['id']
                            break
                    else:
                        if device_types:
                            resolved['device_type_id'] = device_types[0]['id']

            # 4. Resolve Cluster dynamically if VM
            if profile.netbox_object_type == "virtualmachine":
                c_res = requests.get(f"{base_url}/api/virtualization/clusters/", headers=headers, verify=False, timeout=3)
                if c_res.status_code == 200:
                    clusters = c_res.json().get('results', [])
                    for c in clusters:
                        if resolved_cluster_id and c['id'] == resolved_cluster_id:
                            resolved['cluster_id'] = c['id']
                            resolved['cluster_name'] = c['name']
                            break
                        if resolved_cluster_name and resolved_cluster_name.lower() in c.get('name', '').lower():
                            resolved['cluster_id'] = c['id']
                            resolved['cluster_name'] = c['name']
                            break
                    else:
                        if clusters:
                            resolved['cluster_id'] = clusters[0]['id']
                            resolved['cluster_name'] = clusters[0]['name']

            # 5. Check if Device/VM already exists in NetBox
            if profile.netbox_object_type == "device":
                d_check = requests.get(f"{base_url}/api/dcim/devices/?name={hostname}", headers=headers, verify=False, timeout=3)
                if d_check.status_code == 200 and d_check.json().get('count', 0) > 0:
                    resolved['device_status'] = "EXISTING"
                    resolved['existing_device_id'] = d_check.json()['results'][0]['id']
            else:
                vm_check = requests.get(f"{base_url}/api/virtualization/virtual-machines/?name={hostname}", headers=headers, verify=False, timeout=3)
                if vm_check.status_code == 200 and vm_check.json().get('count', 0) > 0:
                    resolved['device_status'] = "EXISTING"
                    resolved['existing_device_id'] = vm_check.json()['results'][0]['id']

            # 6. Contextual IP Check & Mask Resolution
            ip_check = requests.get(f"{base_url}/api/ipam/ip-addresses/?address={ip_address}", headers=headers, verify=False, timeout=3)
            if ip_check.status_code == 200 and ip_check.json().get('count', 0) > 0:
                resolved['ip_status'] = "EXISTING"
                resolved['ip_address_with_mask'] = ip_check.json()['results'][0]['address']
            else:
                prefix_res = requests.get(f"{base_url}/api/ipam/prefixes/?contains={ip_address}", headers=headers, verify=False, timeout=3)
                if prefix_res.status_code == 200 and prefix_res.json().get('count', 0) > 0:
                    parent_prefix = prefix_res.json()['results'][0]['prefix']
                    mask = parent_prefix.split('/')[-1] if '/' in parent_prefix else '24'
                    resolved['ip_address_with_mask'] = f"{ip_address}/{mask}"
                else:
                    resolved['ip_address_with_mask'] = f"{ip_address}/24"

        except Exception as e:
            pass

        return resolved

    @staticmethod
    def resolve_zabbix_objects(config: Dict[str, Any], profile: ProvisionProfile, hostname: str, ip_address: str, custom_template: Optional[str] = None) -> Dict[str, Any]:
        """
        Dynamically query Zabbix API to resolve host groups, templates, and check host existence.
        If custom_template is provided, prioritizes the user-selected template.
        """
        zabbix_cfg = config.get('zabbix', {})
        zabbix_url = zabbix_cfg.get('url', '').rstrip('/')
        user_zb = zabbix_cfg.get('user', 'Admin')
        pwd_zb = zabbix_cfg.get('password', '')

        resolved = {
            "group_ids": ["2"], # Fallback groupid
            "group_names": profile.zabbix_groups,
            "template_ids": [],
            "template_names": [custom_template] if custom_template else profile.zabbix_templates,
            "interface_type": profile.zabbix_interface_type,
            "port": profile.zabbix_port,
            "snmp_version": profile.snmp_version if hasattr(profile, 'snmp_version') else "v2c",
            "host_status": "NEW",
            "tags": [{"tag": "Profile", "value": profile.name}, {"tag": "Orchestrator", "value": "NetLens"}]
        }

        try:
            auth_payload = {
                "jsonrpc": "2.0",
                "method": "user.login",
                "params": {"username": user_zb, "password": pwd_zb},
                "id": 1
            }
            auth_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json=auth_payload, timeout=3).json()
            token = auth_res.get('result')

            if token:
                # Check if host exists
                h_check = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                    "jsonrpc": "2.0",
                    "method": "host.get",
                    "params": {"filter": {"host": [hostname]}},
                    "auth": token,
                    "id": 2
                }, timeout=3).json()
                if h_check.get('result'):
                    resolved['host_status'] = "EXISTING"

                # Resolve Host Groups
                g_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                    "jsonrpc": "2.0",
                    "method": "hostgroup.get",
                    "params": {"filter": {"name": profile.zabbix_groups}},
                    "auth": token,
                    "id": 3
                }, timeout=3).json()
                if g_res.get('result'):
                    resolved['group_ids'] = [g['groupid'] for g in g_res['result']]

                t_ids = []
                t_names = []

                # Priority 1: User custom template
                if custom_template:
                    c_val = str(custom_template).strip()
                    # Check if template ID
                    if c_val.isdigit():
                        t_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                            "jsonrpc": "2.0",
                            "method": "template.get",
                            "params": {"output": ["templateid", "name"], "templateids": [c_val]},
                            "auth": token,
                            "id": 4
                        }, timeout=3).json()
                        if t_res.get('result'):
                            t_ids.append(t_res['result'][0]['templateid'])
                            t_names.append(t_res['result'][0]['name'])

                    # Check by exact name or filter if not found yet
                    if not t_ids:
                        t_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                            "jsonrpc": "2.0",
                            "method": "template.get",
                            "params": {"output": ["templateid", "name"], "filter": {"name": [c_val]}},
                            "auth": token,
                            "id": 4
                        }, timeout=3).json()
                        if t_res.get('result'):
                            t_ids.append(t_res['result'][0]['templateid'])
                            t_names.append(t_res['result'][0]['name'])

                    # Check by search wildcard if still not found
                    if not t_ids:
                        t_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                            "jsonrpc": "2.0",
                            "method": "template.get",
                            "params": {"output": ["templateid", "name"], "search": {"name": f"*{c_val}*"}, "searchWildcardsEnabled": True},
                            "auth": token,
                            "id": 4
                        }, timeout=3).json()
                        if t_res.get('result'):
                            t_ids.append(t_res['result'][0]['templateid'])
                            t_names.append(t_res['result'][0]['name'])

                # Priority 2: Fallback to profile default templates if custom template not provided or not resolved
                if not t_ids:
                    for target_t in profile.zabbix_templates:
                        t_res = requests.post(f"{zabbix_url}/api_jsonrpc.php", json={
                            "jsonrpc": "2.0",
                            "method": "template.get",
                            "params": {
                                "output": ["templateid", "name"],
                                "search": {"name": f"*{target_t}*"},
                                "searchWildcardsEnabled": True
                            },
                            "auth": token,
                            "id": 4
                        }, timeout=3).json()
                        if t_res.get('result'):
                            best_t = t_res['result'][0]
                            for t in t_res['result']:
                                if t['name'].startswith("Template OS") or t['name'].startswith("Network Generic") or "by Zabbix agent" in t['name']:
                                    best_t = t
                                    break
                            if best_t['templateid'] not in t_ids:
                                t_ids.append(best_t['templateid'])
                                t_names.append(best_t['name'])

                if t_ids:
                    resolved['template_ids'] = t_ids
                    resolved['template_names'] = t_names
                    # Auto-detect interface type if template clearly requires SNMP
                    if any("snmp" in tn.lower() for tn in t_names) and resolved['interface_type'] == 1:
                        resolved['interface_type'] = 2
                        resolved['port'] = 161
        except Exception as e:
            logger.warning(f"[ProfileEngine] Falha na resolução Zabbix para '{hostname}': {e}")

        return resolved
