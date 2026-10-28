import requests
from typing import Dict, Any, Optional
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("netbox_provisioner")

class NetBoxProvisioner:
    """Provisioning driver for NetBox DCIM/IPAM API."""

    @staticmethod
    def provision(inp: Dict[str, Any], config: Dict[str, Any], resolved: Optional[Dict[str, Any]] = None, action: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute NetBox provisioning: create device/VM, create interface, allocate IP, set primary IP.
        
        Args:
            inp: Canonical input data (hostname, ip, etc.)
            config: Full config dict from config.json
            resolved: NetBox resolved objects (site_id, role_id, device_type_id, etc.)
            action: Action ('CREATE' or 'REUSE')
        
        Returns:
            Dict with keys: status ('PASS' or 'FAIL'), message
        """
        try:
            if action == "REUSE":
                return {"status": "PASS", "message": f"Device {inp.get('hostname')} já existente no NetBox (REUSE)."}

            netbox_cfg = config.get('netbox', {})
            base_url = netbox_cfg.get('url', '').rstrip('/')
            if not base_url:
                raise ValueError("NetBox URL não configurada em config.json")
            token = netbox_cfg.get('api_token', '')
            headers = {"Authorization": f"Token {token}", "Content-Type": "application/json", "Accept": "application/json"}

            requests.packages.urllib3.disable_warnings()

            netbox_resolved = resolved or {}
            is_vm = (netbox_resolved.get("object_type") == "virtualmachine")

            # Build payload according to object type
            if is_vm:
                ep = f"{base_url}/api/virtualization/virtual-machines/"
                cluster_id = netbox_resolved.get("cluster_id", 18)
                payload = {
                    "name": inp['hostname'],
                    "cluster": cluster_id,
                    "status": "active"
                }
                # Do NOT send site on VM creation; NetBox infers/assigns the site from the cluster automatically.
                if netbox_resolved.get("role_id"):
                    payload["role"] = netbox_resolved.get("role_id")

                vcpus_raw = netbox_resolved.get("vcpus")
                if vcpus_raw:
                    try:
                        vcpus_clean = str(vcpus_raw).lower().replace('cores', '').replace('core', '').replace('vcpus', '').replace('vcpu', '').strip()
                        payload["vcpus"] = float(vcpus_clean)
                    except (ValueError, TypeError): pass

                mem_raw = netbox_resolved.get("memory")
                if mem_raw:
                    try:
                        m_str = str(mem_raw).strip().upper().replace('MB', '').replace('M', '')
                        if 'G' in m_str:
                            m_num = float(m_str.replace('GB', '').replace('G', '').strip())
                            payload["memory"] = int(m_num * 1024)
                        else:
                            m_num = float(m_str)
                            if m_num <= 128:
                                payload["memory"] = int(m_num * 1024)
                            else:
                                payload["memory"] = int(m_num)
                    except (ValueError, TypeError): pass

                disk_raw = netbox_resolved.get("disk")
                if disk_raw:
                    try:
                        d_str = str(disk_raw).strip().upper().replace('GB', '').replace('G', '').replace('T', '000').strip()
                        payload["disk"] = int(float(d_str))
                    except (ValueError, TypeError): pass

                if netbox_resolved.get("custom_fields"):
                    payload["custom_fields"] = netbox_resolved["custom_fields"]
            else:
                ep = f"{base_url}/api/dcim/devices/"
                payload = {
                    "name": inp['hostname'],
                    "device_type": netbox_resolved.get("device_type_id"),
                    "role": netbox_resolved.get("role_id"),
                    "site": netbox_resolved.get("site_id"),
                    "status": "active"
                }
                if netbox_resolved.get("custom_fields"):
                    payload["custom_fields"] = netbox_resolved["custom_fields"]

            nb_res = requests.post(ep, json=payload, headers=headers, verify=False, timeout=4)
            dev_id = None
            if nb_res.status_code in [200, 201]:
                dev_id = nb_res.json().get('id')
            elif nb_res.status_code == 400 and ("already exists" in nb_res.text or "duplicate" in nb_res.text):
                if is_vm:
                    d_get = requests.get(f"{base_url}/api/virtualization/virtual-machines/?name={inp['hostname']}", headers=headers, verify=False, timeout=3)
                else:
                    d_get = requests.get(f"{base_url}/api/dcim/devices/?name={inp['hostname']}", headers=headers, verify=False, timeout=3)
                if d_get.status_code == 200 and d_get.json().get('results'):
                    dev_id = d_get.json()['results'][0]['id']

            if dev_id:
                # Create or get interface eth0
                intf_id = None
                if is_vm:
                    intf_ep = f"{base_url}/api/virtualization/interfaces/"
                    intf_payload = {"virtual_machine": dev_id, "name": "eth0", "enabled": True}
                    intf_query = f"{base_url}/api/virtualization/interfaces/?virtual_machine_id={dev_id}"
                    assigned_type = "virtualization.vminterface"
                else:
                    intf_ep = f"{base_url}/api/dcim/interfaces/"
                    intf_payload = {"device": dev_id, "name": "eth0", "type": "other"}
                    intf_query = f"{base_url}/api/dcim/interfaces/?device_id={dev_id}"
                    assigned_type = "dcim.interface"

                intf_res = requests.post(intf_ep, json=intf_payload, headers=headers, verify=False, timeout=3)
                if intf_res.status_code in [200, 201]:
                    intf_id = intf_res.json().get('id')
                else:
                    intf_list = requests.get(intf_query, headers=headers, verify=False, timeout=3)
                    if intf_list.status_code == 200 and intf_list.json().get('results'):
                        intf_id = intf_list.json()['results'][0]['id']

                # Create or update IP address and assign to interface
                ip_id = None
                ip_mask = netbox_resolved.get("ip_address_with_mask", f"{inp.get('ip', '')}/24")
                ip_payload = {"address": ip_mask, "status": "active"}
                if intf_id:
                    ip_payload["assigned_object_type"] = assigned_type
                    ip_payload["assigned_object_id"] = intf_id

                ip_res = requests.post(f"{base_url}/api/ipam/ip-addresses/", json=ip_payload, headers=headers, verify=False, timeout=3)
                if ip_res.status_code in [200, 201]:
                    ip_id = ip_res.json().get('id')
                else:
                    ip_list = requests.get(f"{base_url}/api/ipam/ip-addresses/?address={ip_mask}", headers=headers, verify=False, timeout=3)
                    if ip_list.status_code == 200 and ip_list.json().get('results'):
                        ip_id = ip_list.json()['results'][0]['id']
                        requests.patch(f"{base_url}/api/ipam/ip-addresses/{ip_id}/", json=ip_payload, headers=headers, verify=False, timeout=3)

                # Set Primary IPv4
                if ip_id:
                    if is_vm:
                        requests.patch(f"{base_url}/api/virtualization/virtual-machines/{dev_id}/", json={"primary_ip4": ip_id}, headers=headers, verify=False, timeout=3)
                    else:
                        requests.patch(f"{base_url}/api/dcim/devices/{dev_id}/", json={"primary_ip4": ip_id}, headers=headers, verify=False, timeout=3)

                obj_label = "VM" if is_vm else "Device"
                return {"status": "PASS", "message": f"{obj_label} {inp['hostname']} ({ip_mask}) criado/atualizado com sucesso no NetBox!"}
            else:
                return {"status": "FAIL", "message": f"NetBox respondeu {nb_res.status_code}: {SecretSanitizer.sanitize_text(nb_res.text)}"}
        except Exception as e:
            return {"status": "FAIL", "message": f"Erro NetBox: {SecretSanitizer.sanitize_exception(e)}"}
