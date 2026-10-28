from app.services.config_service import ConfigService
from app.clients.zabbix import ZabbixClient
from app.clients.netdisco import NetdiscoClient
from app.clients.librenms import LibreNMSClient

_zabbix_client = None
_netdisco_client = None
_librenms_client = None

def is_mock_mode():
    config = ConfigService.load_config()
    netdisco_cfg = config.get("netdisco", {})
    librenms_cfg = config.get("librenms", {})
    zabbix_cfg = config.get("zabbix", {})
    
    # If standard placeholders or empty config, run in Mock mode
    if (not netdisco_cfg or
        netdisco_cfg.get("password") == "SUA_SENHA_AQUI" or 
        librenms_cfg.get("password") == "SUA_SENHA_AQUI" or 
        zabbix_cfg.get("password") == "SUA_SENHA_AQUI"):
        return True
    return False

def get_zabbix_client():
    global _zabbix_client
    if is_mock_mode():
        return None
    if _zabbix_client is None:
        config = ConfigService.load_config()
        zabbix_cfg = config.get("zabbix", {})
        verify_ssl = config.get("settings", {}).get("verify_ssl", False)
        _zabbix_client = ZabbixClient(
            url=zabbix_cfg.get("url"),
            user=zabbix_cfg.get("user"),
            password=zabbix_cfg.get("password"),
            verify_ssl=verify_ssl
        )
    return _zabbix_client

def get_netdisco_client():
    global _netdisco_client
    if is_mock_mode():
        return None
    if _netdisco_client is None:
        config = ConfigService.load_config()
        netdisco_cfg = config.get("netdisco", {})
        verify_ssl = config.get("settings", {}).get("verify_ssl", False)
        _netdisco_client = NetdiscoClient(
            url=netdisco_cfg.get("url"),
            user=netdisco_cfg.get("user"),
            password=netdisco_cfg.get("password"),
            api_token=netdisco_cfg.get("api_token"),
            verify_ssl=verify_ssl,
            db_config=config.get("databases", {}).get("netdisco")
        )
    return _netdisco_client

def get_librenms_client():
    global _librenms_client
    if is_mock_mode():
        return None
    if _librenms_client is None:
        config = ConfigService.load_config()
        librenms_cfg = config.get("librenms", {})
        verify_ssl = config.get("settings", {}).get("verify_ssl", False)
        _librenms_client = LibreNMSClient(
            url=librenms_cfg.get("url"),
            user=librenms_cfg.get("user"),
            password=librenms_cfg.get("password"),
            api_token=librenms_cfg.get("api_token"),
            verify_ssl=verify_ssl,
            db_config=config.get("databases", {}).get("librenms")
        )
    return _librenms_client
