from app.models.constants import Vendor, Platform, DeviceRole, DeviceStatus

class DeviceIdentity:
    def __init__(self, device_id: str, hostname: str, serial: str = None, management_ip: str = None, vendor: Vendor = Vendor.UNKNOWN, platform: Platform = Platform.UNKNOWN, model: str = None):
        # Compatibility check for old positional arguments: (device_id, hostname, vendor, platform, management_ip)
        # If the 3rd argument is a Vendor (or maps to one) or 4th is a Platform (or maps to one), remap them.
        is_old_vendor = isinstance(serial, Vendor) or (isinstance(serial, str) and serial in [v.value for v in Vendor])
        is_old_platform = isinstance(management_ip, Platform) or (isinstance(management_ip, str) and management_ip in [p.value for p in Platform])
        
        if is_old_vendor or is_old_platform:
            real_vendor = serial
            real_platform = management_ip
            # In old positional signature, management_ip was passed in the 5th position (which maps to 'vendor' parameter here)
            real_management_ip = vendor if isinstance(vendor, str) else None
            real_serial = None
            
            if isinstance(real_vendor, str):
                for v in Vendor:
                    if v.value == real_vendor or v.name == real_vendor:
                        real_vendor = v
                        break
            if isinstance(real_platform, str):
                for p in Platform:
                    if p.value == real_platform or p.name == real_platform:
                        real_platform = p
                        break
                        
            self.device_id = device_id
            self.hostname = hostname
            self.serial = real_serial
            self.management_ip = real_management_ip
            self.vendor = real_vendor
            self.platform = real_platform
            self.model = model
        else:
            self.device_id = device_id
            self.hostname = hostname
            self.serial = serial
            self.management_ip = management_ip
            self.vendor = vendor if isinstance(vendor, Vendor) else Vendor(vendor) if vendor in [v.value for v in Vendor] else Vendor.UNKNOWN
            self.platform = platform if isinstance(platform, Platform) else Platform(platform) if platform in [p.value for p in Platform] else Platform.UNKNOWN
            self.model = model

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "hostname": self.hostname,
            "serial": self.serial,
            "management_ip": self.management_ip,
            "vendor": self.vendor.value if isinstance(self.vendor, Vendor) else self.vendor,
            "platform": self.platform.value if isinstance(self.platform, Platform) else self.platform,
            "model": self.model
        }

class NetworkDevice:
    def __init__(self, identity: DeviceIdentity, role: DeviceRole = DeviceRole.ACCESS, status: DeviceStatus = DeviceStatus.ACTIVE, os_version: str = None, site: str = None, source: str = None):
        self.identity = identity
        self.role = role
        self.status = status
        self.os_version = os_version
        self.site = site
        self.source = source

    def to_dict(self):
        data = self.identity.to_dict()
        data.update({
            "role": self.role.value if isinstance(self.role, DeviceRole) else self.role,
            "status": self.status.value if isinstance(self.status, DeviceStatus) else self.status,
            "os_version": self.os_version,
            "site": self.site,
            "source": self.source
        })
        return data
