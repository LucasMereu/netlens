from typing import Dict, Any, List
from app.models.change_plan import ChangePlan
from app.models.device import NetworkDevice
from app.models.constants import DeviceStatus
from app.drivers.base_driver import NetworkDriver
from app.drivers.errors import ValidationError

class PreFlightValidator:
    @staticmethod
    def validate(change_plan: ChangePlan, drivers: Dict[str, NetworkDriver], force: bool = False) -> List[str]:
        errors = []
        
        # 1. Verify ChangePlan approval
        if change_plan.status not in (ChangePlan.APPROVED, ChangePlan.LOCKING, ChangePlan.PREFLIGHT):
            errors.append(f"ChangePlan {change_plan.id} nao esta APROVADO. Status atual: {change_plan.status}")
            
        # 2. Check each target device status
        for dev_ip, driver in drivers.items():
            # Test connectivity
            try:
                driver.connect()
                dev_info = driver.get_device_info()
                
                # Check platform
                if dev_info.get("vendor") != driver.identity.vendor:
                    errors.append(f"Fabricante retornado pelo switch {dev_ip} ({dev_info.get('vendor')}) diverge do configurado ({driver.identity.vendor.value}).")
                
                # Check maintenance mode (if mock network device or driver represents maintenance)
                # NetworkDevice status == MAINTENANCE
                if driver.identity.model == "MAINTENANCE" and not force:
                    errors.append(f"Switch {dev_ip} esta em MODO DE MANUTENCAO. Operacao bloqueada.")
                    
            except Exception as e:
                errors.append(f"Switch {dev_ip} inacessivel ou erro de autenticacao: {e}")
            finally:
                try:
                    driver.disconnect()
                except:
                    pass
                    
        if errors:
            raise ValidationError("Falha no Pre-Flight:\n" + "\n".join(errors))
            
        return ["Reachable Check: PASS", "Platform Check: PASS", "Approval Check: PASS"]
