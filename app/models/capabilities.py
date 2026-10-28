class DeviceCapabilities:
    def __init__(self, supports_vlan_create: bool = False, supports_vlan_delete: bool = False, supports_access_port: bool = False, supports_trunk_port: bool = False, supports_trunk_vlan_add: bool = False, supports_trunk_vlan_remove: bool = False, supports_lldp: bool = False, supports_cdp: bool = False, supports_stp: bool = False, supports_config_save: bool = False, supports_config_rollback: bool = False, supports_config_revision: bool = False):
        self.supports_vlan_create = supports_vlan_create
        self.supports_vlan_delete = supports_vlan_delete
        self.supports_access_port = supports_access_port
        self.supports_trunk_port = supports_trunk_port
        self.supports_trunk_vlan_add = supports_trunk_vlan_add
        self.supports_trunk_vlan_remove = supports_trunk_vlan_remove
        self.supports_lldp = supports_lldp
        self.supports_cdp = supports_cdp
        self.supports_stp = supports_stp
        self.supports_config_save = supports_config_save
        self.supports_config_rollback = supports_config_rollback
        self.supports_config_revision = supports_config_revision

    def to_dict(self):
        return {
            "supports_vlan_create": self.supports_vlan_create,
            "supports_vlan_delete": self.supports_vlan_delete,
            "supports_access_port": self.supports_access_port,
            "supports_trunk_port": self.supports_trunk_port,
            "supports_trunk_vlan_add": self.supports_trunk_vlan_add,
            "supports_trunk_vlan_remove": self.supports_trunk_vlan_remove,
            "supports_lldp": self.supports_lldp,
            "supports_cdp": self.supports_cdp,
            "supports_stp": self.supports_stp,
            "supports_config_save": self.supports_config_save,
            "supports_config_rollback": self.supports_config_rollback,
            "supports_config_revision": self.supports_config_revision
        }
