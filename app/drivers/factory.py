from typing import Optional
from app.models.constants import Vendor, Platform
from app.models.device import DeviceIdentity
from app.drivers.base_driver import NetworkDriver
from app.drivers.dell.driver import DellDriver
from app.drivers.mock.driver import MockNetworkDriver
from app.drivers.aruba.driver import ArubaDriver
from app.drivers.comware.driver import ComwareDriver
from app.drivers.hp.driver import HPDriver
from app.drivers.threecom.driver import ThreeComDriver
from app.drivers.stanton.driver import StantonDriver
from app.drivers.errors import UnsupportedDeviceError

class NetworkDriverFactory:
    @staticmethod
    def get_driver(identity: DeviceIdentity, username: Optional[str] = None, password: Optional[str] = None) -> NetworkDriver:
        vendor = identity.vendor
        platform = identity.platform
        
        if vendor == Vendor.MOCK:
            return MockNetworkDriver(identity)
            
        elif vendor == Vendor.DELL:
            if platform == Platform.DELL_OS9:
                return DellDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante DELL.")
                
        elif vendor == Vendor.ARUBA:
            if platform == Platform.ARUBA_AOSS:
                return ArubaDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante ARUBA.")
                
        elif vendor == Vendor.HPE:
            if platform == Platform.HPE_COMWARE:
                return ComwareDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante HPE.")
                
        elif vendor == Vendor.HP:
            if platform == Platform.HP_PROCURVE:
                return HPDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante HP.")

        elif vendor == Vendor.THRECOM:
            if platform == Platform.COMWARE_V5:
                return ThreeComDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante 3COM.")

        elif vendor == Vendor.STANTON:
            if platform == Platform.STANTON_OS:
                return StantonDriver(identity, username=username, password=password)
            else:
                raise UnsupportedDeviceError(f"Plataforma '{platform}' nao suportada para o fabricante STANTON.")

        else:
            raise UnsupportedDeviceError(f"Fabricante desconhecido ou nao suportado: {vendor}")
