from typing import Dict, Any, Optional
from app.models.device_identity import CanonicalDevice
from app.drivers.errors import ValidationError

class IdentityResolver:
    @staticmethod
    def resolve(netbox_data: Dict[str, Any], hardware_data: Dict[str, Any]) -> CanonicalDevice:
        """
        Unifica identidades de fontes diferentes e checa conflitos.
        Regras hierarquicas:
        1. Serial + Manufacturer
        2. Serial
        3. Management IP + Platform
        4. Management IP
        """
        nb_serial = netbox_data.get("serial")
        hw_serial = hardware_data.get("serial")
        
        nb_ip = netbox_data.get("management_ip")
        hw_ip = hardware_data.get("management_ip")
        
        # Conflict Check: same IP but different serials
        if nb_ip and hw_ip and nb_ip == hw_ip:
            if nb_serial and hw_serial and nb_serial != hw_serial:
                raise ValidationError(f"IDENTITY_CONFLICT: O IP {nb_ip} possui o serial {nb_serial} no NetBox mas o serial {hw_serial} no Hardware.")

        # Hierarchical resolution
        serial = hw_serial or nb_serial
        ip = hw_ip or nb_ip
        manufacturer = hardware_data.get("manufacturer") or netbox_data.get("manufacturer")
        platform = hardware_data.get("platform") or netbox_data.get("platform")
        
        canonical_id = f"device-{serial}" if serial else f"device-{ip}"
        
        dev = CanonicalDevice(
            canonical_id=canonical_id,
            serial=serial,
            management_ip=ip,
            manufacturer=manufacturer,
            platform=platform
        )
        
        dev.source_ids["netbox"] = netbox_data.get("device_id")
        dev.source_ids["hardware"] = hardware_data.get("device_id")
        return dev
