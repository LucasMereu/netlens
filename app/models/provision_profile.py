from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ProvisionProfile:
    name: str
    description: str
    netbox_role_slug: str
    netbox_object_type: str  # "device" or "virtualmachine"
    zabbix_groups: List[str]
    zabbix_templates: List[str]
    zabbix_interface_type: int  # 1=Agent, 2=SNMP
    zabbix_port: int
    librenms_protocol: str  # "snmp", "ping"
    librenms_version: str   # "v2c", "v3", "none"
    librenms_port: int
    netdisco_discovery_enabled: bool
    netdisco_protocols: List[str]
    snmp_version: str = "v2c"
    default_cluster: str = ""

BUILTIN_PROFILES: Dict[str, ProvisionProfile] = {
    "NETWORK_SWITCH": ProvisionProfile(
        name="NETWORK_SWITCH",
        description="Switch de Acesso, Agregação ou Core (HPE, Aruba, Cisco, Dell, 3Com)",
        netbox_role_slug="switch",
        netbox_object_type="device",
        zabbix_groups=["Network Devices"],
        zabbix_templates=["Template Net Network Generic SNMP"],
        zabbix_interface_type=2,
        zabbix_port=161,
        snmp_version="v2c",
        librenms_protocol="snmp",
        librenms_version="v2c",
        librenms_port=161,
        netdisco_discovery_enabled=True,
        netdisco_protocols=["LLDP", "CDP"]
    ),
    "ROUTER_CISCO": ProvisionProfile(
        name="ROUTER_CISCO",
        description="Roteadores de Borda / WAN Cisco / Mikrotik",
        netbox_role_slug="link",
        netbox_object_type="device",
        zabbix_groups=["Network Devices"],
        zabbix_templates=["Template Net Cisco IOS SNMP"],
        zabbix_interface_type=2,
        zabbix_port=161,
        snmp_version="v2c",
        librenms_protocol="snmp",
        librenms_version="v2c",
        librenms_port=161,
        netdisco_discovery_enabled=True,
        netdisco_protocols=["LLDP", "CDP"]
    ),
    "FIREWALL_SOPHOS": ProvisionProfile(
        name="FIREWALL_SOPHOS",
        description="Firewalls de Borda Sophos XGS / Fortinet",
        netbox_role_slug="firewall",
        netbox_object_type="device",
        zabbix_groups=["Firewalls"],
        zabbix_templates=["Template Net Sophos XGS SNMP"],
        zabbix_interface_type=2,
        zabbix_port=161,
        snmp_version="v2c",
        librenms_protocol="snmp",
        librenms_version="v2c",
        librenms_port=161,
        netdisco_discovery_enabled=True,
        netdisco_protocols=["LLDP", "CDP"]
    ),
    "SERVER_LINUX": ProvisionProfile(
        name="SERVER_LINUX",
        description="Servidores Físicos Linux (Dell, HP, Lenovo)",
        netbox_role_slug="servidores",
        netbox_object_type="device",
        zabbix_groups=["Linux servers"],
        zabbix_templates=["Linux by Zabbix agent"],
        zabbix_interface_type=1,
        zabbix_port=10050,
        snmp_version="none",
        librenms_protocol="snmp",
        librenms_version="v2c",
        librenms_port=161,
        netdisco_discovery_enabled=False,
        netdisco_protocols=[]
    ),
    "VM_PROXMOX": ProvisionProfile(
        name="VM_PROXMOX",
        description="Máquinas Virtuais / Containers Proxmox VE",
        netbox_role_slug="vm",
        netbox_object_type="virtualmachine",
        zabbix_groups=["Discovered hosts"],
        zabbix_templates=["Linux by Zabbix agent"],
        zabbix_interface_type=1,
        zabbix_port=10050,
        snmp_version="none",
        librenms_protocol="ping",
        librenms_version="none",
        librenms_port=0,
        netdisco_discovery_enabled=False,
        netdisco_protocols=[],
        default_cluster="18"
    )
}
