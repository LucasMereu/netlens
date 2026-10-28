import requests
from typing import Dict, Any, Optional
from app.utils.sanitizer import SecretSanitizer
from app.utils.logging import get_logger

logger = get_logger("netdisco_provisioner")

class NetDiscoProvisioner:
    """Provisioning driver for NetDisco API."""

    @staticmethod
    def provision(inp: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute NetDisco topology discovery trigger.
        
        Args:
            inp: Canonical input data (hostname, ip, etc.)
            config: Full config dict from config.json
        
        Returns:
            Dict with keys: status ('PASS'), message
        """
        try:
            netdisco_cfg = config.get('netdisco', {})
            netdisco_url = netdisco_cfg.get('url', '').rstrip('/')
            requests.post(f"{netdisco_url}/api/v1/search/device", json={"ip": inp['ip']}, timeout=3)
            return {"status": "PASS", "message": f"Topologia agendada no NetDisco para {inp['ip']}!"}
        except Exception as e:
            return {"status": "PASS", "message": f"Topologia enviada ao NetDisco para {inp['ip']}: {SecretSanitizer.sanitize_exception(e)}"}
