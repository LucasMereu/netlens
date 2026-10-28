from flask import Blueprint, jsonify
from app.services.config_service import ConfigService
from app.clients import get_zabbix_client, get_netdisco_client, get_librenms_client, is_mock_mode

status_bp = Blueprint('status', __name__)

@status_bp.route('/api/status')
def get_status():
    config = ConfigService.load_config()
    urls = {
        "netbox": config.get("netbox", {}).get("url", ""),
        "netdisco": config.get("netdisco", {}).get("url", ""),
        "librenms": config.get("librenms", {}).get("url", ""),
        "zabbix": config.get("zabbix", {}).get("url", "")
    }

    # Mapeamento de servidores dinâmicos para a barra de cabeçalho
    def _build_servers_status(is_mock=False):
        res = []
        for srv in config.get("servers", []):
            if not srv.get("enabled", True):
                continue
            srv_type = srv.get("type", "generic")
            if is_mock:
                status_val = "Mocked (OK)"
            elif srv_type == "zabbix":
                status_val = z_status
            elif srv_type == "netdisco":
                status_val = n_status
            elif srv_type == "librenms":
                status_val = l_status
            elif srv_type == "netbox":
                status_val = netbox_status
            else:
                status_val = "Online" if srv.get("url") else "Nao Configurado"

            is_online = ("Online" in status_val) or ("OK" in status_val)
            res.append({
                "id": srv.get("id"),
                "name": srv.get("name"),
                "type": srv_type,
                "url": srv.get("url"),
                "status": status_val,
                "online": is_online,
                "show_in_header": bool(srv.get("show_in_header", True))
            })
        return res

    if is_mock_mode():
        return jsonify({
            "mode": "mock",
            "netbox": "Mocked (OK)",
            "zabbix": "Mocked (OK)",
            "netdisco": "Mocked (OK)",
            "librenms": "Mocked (OK)",
            "urls": urls,
            "servers": _build_servers_status(is_mock=True),
            "config": config
        })
    
    zabbix_client = get_zabbix_client()
    z_status = "Nao Configurado"
    if zabbix_client:
        try:
            zabbix_client.login()
            z_status = "Online"
        except Exception as e:
            z_status = f"Erro: {str(e)}"

    netdisco_client = get_netdisco_client()
    n_status = "Nao Configurado"
    if netdisco_client:
        try:
            netdisco_client.login()
            n_status = "Online"
        except Exception as e:
            n_status = f"Erro: {str(e)}"

    librenms_client = get_librenms_client()
    l_status = "Nao Configurado"
    if librenms_client:
        try:
            librenms_client.get_devices()
            l_status = "Online"
        except Exception as e:
            l_status = f"Erro: {str(e)}"

    netbox_status = "Online" if config.get("netbox", {}).get("url") else "Nao Configurado"

    return jsonify({
        "mode": "real",
        "netbox": netbox_status,
        "zabbix": z_status,
        "netdisco": n_status,
        "librenms": l_status,
        "urls": urls,
        "servers": _build_servers_status(is_mock=False)
    })
