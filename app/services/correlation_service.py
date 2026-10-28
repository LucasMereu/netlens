from datetime import datetime
from typing import Dict, Any, List
from app.models.canonical_state import CanonicalObservedState, CanonicalProperty
from app.services.source_of_truth_service import SourceOfTruthService

class CorrelationService:
    @staticmethod
    def correlate_property(field: str, sources_dict: Dict[str, Any], observed_at_dict: Dict[str, str]) -> CanonicalProperty:
        """
        Retorna a propriedade canonical com confianca baseada na matriz de autoridade:
        - AUTHORITATIVE para a autoridade
        - CORROBORATING se o valor bate com a autoridade
        - CONFLICTING se o valor diverge
        """
        auth_src = SourceOfTruthService.get_authority(field)
        auth_val = sources_dict.get(auth_src)
        
        # Determine confidence of the winning source
        # Let's say we output the authoritative value
        val = auth_val
        src = auth_src
        observed_at = observed_at_dict.get(auth_src, datetime.utcnow().isoformat() + "Z")
        
        # Check conflicts
        has_conflict = False
        for s, v in sources_dict.items():
            if s != auth_src and v != auth_val:
                has_conflict = True
                
        confidence = "CONFLICTING" if has_conflict else "AUTHORITATIVE"
        return CanonicalProperty(value=val, source=src, observed_at=observed_at, confidence=confidence)

    @staticmethod
    def correlate_device(device_id: str, netbox_data: Dict[str, Any], hardware_data: Dict[str, Any], netdisco_data: Dict[str, Any]) -> CanonicalObservedState:
        state = CanonicalObservedState(device_id)
        
        now_str = datetime.utcnow().isoformat() + "Z"
        
        # Hostname Correlation
        host_sources = {"netbox": netbox_data.get("hostname"), "hardware": hardware_data.get("hostname"), "netdisco": netdisco_data.get("hostname")}
        host_times = {"netbox": netbox_data.get("observed_at", now_str), "hardware": hardware_data.get("observed_at", now_str), "netdisco": netdisco_data.get("observed_at", now_str)}
        state.hostname = CorrelationService.correlate_property("hostname", host_sources, host_times)
        
        # Serial Correlation
        serial_sources = {"netbox": netbox_data.get("serial"), "hardware": hardware_data.get("serial")}
        serial_times = {"netbox": netbox_data.get("observed_at", now_str), "hardware": hardware_data.get("observed_at", now_str)}
        state.serial = CorrelationService.correlate_property("serial", serial_sources, serial_times)

        # Platform
        plat_sources = {"netbox": netbox_data.get("platform"), "hardware": hardware_data.get("platform")}
        plat_times = {"netbox": netbox_data.get("observed_at", now_str), "hardware": hardware_data.get("observed_at", now_str)}
        state.platform = CorrelationService.correlate_property("platform", plat_sources, plat_times)

        return state
