import requests
from typing import Dict, Any, Optional
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("librenms_provisioner")

class LibreNMSProvisioner:
    """Provisioning driver for LibreNMS API."""

    @staticmethod
    def provision(inp: Dict[str, Any], config: Dict[str, Any], snmp_community: str = "public", action: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute LibreNMS device enrollment.
        
        Args:
            inp: Canonical input data (hostname, ip, etc.)
            config: Full config dict from config.json
            snmp_community: Decrypted SNMP community string
            action: Action ('CREATE' or 'REUSE')
        
        Returns:
            Dict with keys: status ('PASS' or 'FAIL'), message
        """
        try:
            if action == "REUSE":
                return {"status": "PASS", "message": f"Dispositivo {inp.get('ip')} já cadastrado no LibreNMS (REUSE)."}

            lnms_cfg = config.get('librenms', {})
            lnms_url = lnms_cfg.get('url', '').rstrip('/')
            lnms_token = lnms_cfg.get('api_token', '')

            headers = {"X-Auth-Token": lnms_token, "Content-Type": "application/json"}
            payload = {"hostname": inp['ip'], "version": "v2c", "community": snmp_community, "force_add": True}

            res = requests.post(f"{lnms_url}/api/v0/devices", json=payload, headers=headers, timeout=4)
            # Patch sysName with hostname so LibreNMS UI shows Hostname
            requests.patch(f"{lnms_url}/api/v0/devices/{inp['ip']}", json={"field": "sysName", "value": inp['hostname']}, headers=headers, timeout=3)
            return {"status": "PASS", "message": f"Dispositivo {inp['hostname']} ({inp['ip']}) cadastrado no LibreNMS!"}
        except Exception as e:
            return {"status": "FAIL", "message": f"Erro LibreNMS: {SecretSanitizer.sanitize_exception(e)}"}
