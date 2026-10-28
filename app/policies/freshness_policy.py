from typing import Dict

class FreshnessPolicy:
    TTLS = {
        "hostname": 86400,        # 24h
        "management_ip": 86400,   # 24h
        "serial": 604800,         # 7d
        "platform": 604800,       # 7d
        "topology": 21600,        # 6h
        "interface_status": 300,  # 5min
        "interface_speed": 300,   # 5min
        "lldp_neighbors": 900,    # 15min
        "librenms_telemetry": 300,# 5min
        "zabbix_availability": 120# 2min
    }

    @staticmethod
    def get_ttl(attribute: str) -> int:
        return FreshnessPolicy.TTLS.get(attribute, 300)
