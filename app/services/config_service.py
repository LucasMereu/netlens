import os
import json
from app.utils.logging import get_logger

logger = get_logger("config_service")

class ConfigService:
    _config = None
    _users = None
    _links = None
    _plans = None

    CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
    USERS_PATH = os.path.join(CONFIG_DIR, 'users.json')
    LINKS_PATH = os.path.join(CONFIG_DIR, 'useful_links.json')
    PLANS_PATH = os.path.join(CONFIG_DIR, 'provision_plans.json')

    @classmethod
    def load_config(cls):
        if cls._config is not None:
            return cls._config

        config_data = {}
        if os.path.exists(cls.CONFIG_PATH):
            try:
                with open(cls.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            except Exception as e:
                logger.error(f"Erro ao carregar config.json: {e}")

        # Fallback para variáveis de ambiente
        # Ex: NETLENS_ZABBIX_URL, NETLENS_ZABBIX_USER, NETLENS_ZABBIX_PASSWORD
        zabbix = config_data.setdefault("zabbix", {})
        zabbix["url"] = os.environ.get("NETLENS_ZABBIX_URL", zabbix.get("url", ""))
        zabbix["user"] = os.environ.get("NETLENS_ZABBIX_USER", zabbix.get("user", "admin"))
        zabbix["password"] = os.environ.get("NETLENS_ZABBIX_PASSWORD", zabbix.get("password", "SUA_SENHA_AQUI"))

        netdisco = config_data.setdefault("netdisco", {})
        netdisco["url"] = os.environ.get("NETLENS_NETDISCO_URL", netdisco.get("url", ""))
        netdisco["user"] = os.environ.get("NETLENS_NETDISCO_USER", netdisco.get("user", ""))
        netdisco["password"] = os.environ.get("NETLENS_NETDISCO_PASSWORD", netdisco.get("password", ""))
        netdisco["api_token"] = os.environ.get("NETLENS_NETDISCO_TOKEN", netdisco.get("api_token", ""))

        librenms = config_data.setdefault("librenms", {})
        librenms["url"] = os.environ.get("NETLENS_LIBRENMS_URL", librenms.get("url", ""))
        librenms["user"] = os.environ.get("NETLENS_LIBRENMS_USER", librenms.get("user", ""))
        librenms["password"] = os.environ.get("NETLENS_LIBRENMS_PASSWORD", librenms.get("password", ""))
        librenms["api_token"] = os.environ.get("NETLENS_LIBRENMS_TOKEN", librenms.get("api_token", ""))

        settings = config_data.setdefault("settings", {})
        settings["port"] = int(os.environ.get("NETLENS_PORT", settings.get("port", 5000)))
        settings["verify_ssl"] = os.environ.get("NETLENS_VERIFY_SSL", str(settings.get("verify_ssl", False))).lower() == 'true'

        config_data.setdefault("custom_profiles", {})
        config_data.setdefault("sites", [{"id": "redetv-hq", "name": "RedeTV HQ", "description": "Sede principal"}])
        config_data.setdefault("device_models", [{"id": "hpe-1930-jl685a", "manufacturer": "HPE", "model": "OfficeConnect 1930 JL685A", "default_profile": "NETWORK_SWITCH"}])
        config_data.setdefault("port_events_settings", {
            "flapping_warning_threshold": 3,
            "flapping_critical_threshold": 6,
            "default_window_hours": 24,
            "stp_patterns": [
                "Blocked by STP",
                "BPDU Protection",
                "BPDU",
                "MSTP_BLOCKED",
                "MSTP_DISCARDING",
                "BLOCK_BPDUGUARD",
                "loop-protect",
                "err-disable"
            ]
        })
        config_data.setdefault("bottlenecks_settings", {
            "util_warning_threshold": 75.0,
            "util_critical_threshold": 90.0,
            "ignore_virtual_interfaces": True,
            "min_speed_mbps": 100.0,
            "error_detection_mode": "rate_and_delta",
            "error_min_delta": 5,
            "error_critical_rate": 10.0,
            "discard_min_delta": 50
        })

        if "servers" not in config_data or not config_data.get("servers"):
            default_servers = []
            if config_data.get("netbox", {}).get("url"):
                default_servers.append({
                    "id": "srv-netbox",
                    "name": "Netbox",
                    "type": "netbox",
                    "url": config_data.get("netbox", {}).get("url", ""),
                    "api_token": config_data.get("netbox", {}).get("api_token", ""),
                    "description": "NetBox DCIM / IPAM",
                    "show_in_header": True,
                    "enabled": True
                })
            if config_data.get("netdisco", {}).get("url"):
                default_servers.append({
                    "id": "srv-netdisco",
                    "name": "Netdisco",
                    "type": "netdisco",
                    "url": config_data.get("netdisco", {}).get("url", ""),
                    "user": config_data.get("netdisco", {}).get("user", ""),
                    "password": config_data.get("netdisco", {}).get("password", ""),
                    "api_token": config_data.get("netdisco", {}).get("api_token", ""),
                    "description": "Netdisco Network Discovery",
                    "show_in_header": True,
                    "enabled": True
                })
            if config_data.get("librenms", {}).get("url"):
                default_servers.append({
                    "id": "srv-librenms",
                    "name": "LibreNMS",
                    "type": "librenms",
                    "url": config_data.get("librenms", {}).get("url", ""),
                    "user": config_data.get("librenms", {}).get("user", ""),
                    "password": config_data.get("librenms", {}).get("password", ""),
                    "api_token": config_data.get("librenms", {}).get("api_token", ""),
                    "description": "LibreNMS SNMP Monitoring",
                    "show_in_header": True,
                    "enabled": True
                })
            if config_data.get("zabbix", {}).get("url"):
                default_servers.append({
                    "id": "srv-zabbix",
                    "name": "Zabbix",
                    "type": "zabbix",
                    "url": config_data.get("zabbix", {}).get("url", ""),
                    "user": config_data.get("zabbix", {}).get("user", ""),
                    "password": config_data.get("zabbix", {}).get("password", ""),
                    "description": "Zabbix Monitoring Server",
                    "show_in_header": True,
                    "enabled": True
                })
            config_data["servers"] = default_servers

        if "firewalls" not in config_data or not config_data.get("firewalls"):
            config_data["firewalls"] = [
                {
                    "id": "fw-matriz-sp",
                    "name": "Sophos Matriz SP (F1)",
                    "host": "10.1.1.2",
                    "port": "4444",
                    "city": "São Paulo",
                    "role": "Borda & Datacenter SP",
                    "location": "São Paulo - HQ",
                    "user": "netlens_api",
                    "password": "@NetLensSecurePass2026!",
                    "use_default_auth": True,
                    "enabled": True
                },
                {
                    "id": "fw-brasilia",
                    "name": "Sophos Brasília (F2)",
                    "host": "10.61.0.250",
                    "port": "4444",
                    "city": "Brasília",
                    "role": "Sucursal & Links Brasília",
                    "location": "Brasília - DF",
                    "user": "netlens_api",
                    "password": "@NetLensSecurePass2026!",
                    "use_default_auth": True,
                    "enabled": True
                },
                {
                    "id": "fw-praca-10-65",
                    "name": "Sophos Praça 10.65 (F4)",
                    "host": "10.65.0.250",
                    "port": "4444",
                    "city": "Praça 10.65",
                    "role": "Sucursal & Gateway Remoto",
                    "location": "Praça Remota",
                    "user": "netlens_api",
                    "password": "@NetLensSecurePass2026!",
                    "use_default_auth": True,
                    "enabled": True
                },
                {
                    "id": "fw-str",
                    "name": "Sophos STR (F3)",
                    "host": "10.11.0.253",
                    "port": "4444",
                    "city": "São Paulo - STR",
                    "role": "Firewall Segmento STR",
                    "location": "São Paulo - STR",
                    "user": "netlens_api",
                    "password": "@NetLensSecurePass2026!",
                    "use_default_auth": True,
                    "enabled": True
                }
            ]

        cls._config = config_data
        return cls._config

    @classmethod
    def save_config(cls, config_data):
        import shutil
        cls._config = config_data
        tmp_path = cls.CONFIG_PATH + ".tmp"
        bak_path = cls.CONFIG_PATH + ".bak"
        try:
            if os.path.exists(cls.CONFIG_PATH) and os.path.getsize(cls.CONFIG_PATH) > 0:
                try:
                    shutil.copy2(cls.CONFIG_PATH, bak_path)
                except Exception:
                    pass
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cls.CONFIG_PATH)
            try:
                dir_fd = os.open(cls.CONFIG_DIR, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Erro ao salvar config.json de forma atômica: {e}")

    @classmethod
    def reload_config(cls):
        cls._config = None
        return cls.load_config()

    @classmethod
    def load_users(cls):
        if cls._users is not None:
            return cls._users

        users_data = None
        if os.path.exists(cls.USERS_PATH):
            try:
                with open(cls.USERS_PATH, 'r', encoding='utf-8') as f:
                    users_data = json.load(f)
            except Exception as e:
                logger.error(f"Erro ao carregar users.json: {e}")

        # Default fallback
        if not users_data:
            users_data = {
                "username": "admin",
                "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
                "security_question": "Qual e o nome da empresa?",
                "security_answer_hash": "30cc6dd8ef8458e679e13ae3bf3f634cace9810e2eea03bb6487904595f41056"
            }

        # Normalize to multi-user format while maintaining legacy top-level keys
        if "users" not in users_data or not isinstance(users_data["users"], list):
            main_user = {
                "username": users_data.get("username", "admin"),
                "password_hash": users_data.get("password_hash", "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"),
                "role": "admin",
                "name": "Administrador Principal"
            }
            users_data["users"] = [main_user]

        # Ensure top-level username and password_hash match first admin for legacy callers
        if users_data["users"]:
            users_data["username"] = users_data["users"][0].get("username", "admin")
            users_data["password_hash"] = users_data["users"][0].get("password_hash", "")

        cls._users = users_data
        return cls._users

    @classmethod
    def reload_users(cls):
        cls._users = None
        return cls.load_users()

    @classmethod
    def save_users(cls, users_data):
        cls._users = users_data
        try:
            with open(cls.USERS_PATH, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar users.json: {e}")
        cls.reload_users()

    @classmethod
    def load_links(cls):
        if cls._links is not None:
            return cls._links

        if os.path.exists(cls.LINKS_PATH):
            try:
                with open(cls.LINKS_PATH, 'r', encoding='utf-8') as f:
                    cls._links = json.load(f)
                    return cls._links
            except Exception as e:
                logger.error(f"Erro ao carregar useful_links.json: {e}")
        cls._links = []
        return cls._links

    @classmethod
    def save_links(cls, links_data):
        cls._links = links_data
        try:
            with open(cls.LINKS_PATH, 'w', encoding='utf-8') as f:
                json.dump(links_data, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar useful_links.json: {e}")

    @classmethod
    def load_plans(cls, force_reload: bool = False):
        if cls._plans is not None and not force_reload:
            return cls._plans

        bak_path = cls.PLANS_PATH + ".bak"
        if os.path.exists(cls.PLANS_PATH):
            try:
                with open(cls.PLANS_PATH, 'r', encoding='utf-8') as f:
                    cls._plans = json.load(f)
                    return cls._plans
            except Exception as e:
                logger.error(f"Erro ao carregar provision_plans.json (arquivo corrompido ou inválido): {e}")
                if os.path.exists(bak_path):
                    try:
                        logger.warning("Tentando recuperar plano a partir do arquivo de backup provision_plans.json.bak...")
                        with open(bak_path, 'r', encoding='utf-8') as f_bak:
                            cls._plans = json.load(f_bak)
                            return cls._plans
                    except Exception as e_bak:
                        logger.error(f"Erro ao carregar backup provision_plans.json.bak: {e_bak}")

        cls._plans = {}
        return cls._plans

    @classmethod
    def save_plans(cls, plans_data):
        import shutil
        cls._plans = plans_data
        tmp_path = cls.PLANS_PATH + ".tmp"
        bak_path = cls.PLANS_PATH + ".bak"

        try:
            # 1. Create backup of current valid file if present
            if os.path.exists(cls.PLANS_PATH) and os.path.getsize(cls.PLANS_PATH) > 0:
                try:
                    shutil.copy2(cls.PLANS_PATH, bak_path)
                except Exception:
                    pass

            # 2. Write to .tmp file, flush, and fsync
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(plans_data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())

            # 3. Atomic swap
            os.replace(tmp_path, cls.PLANS_PATH)

            # 4. Fsync parent directory
            try:
                dir_fd = os.open(cls.CONFIG_DIR, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Erro ao salvar de forma atômica o provision_plans.json: {e}")
