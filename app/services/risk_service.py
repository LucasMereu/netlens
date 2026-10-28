from typing import List, Dict, Any
from app.models.constants import OperationType

class RiskService:
    @staticmethod
    def calculate_risk(operations: List[Dict[str, Any]]) -> str:
        """
        Calcula o risco do plano baseado nas operacoes:
        - CREATE_VLAN / DELETE_VLAN: LOW
        - ADD_VLAN_TO_TRUNK / REMOVE_VLAN_FROM_TRUNK: MEDIUM
        - CONFIGURE_ACCESS_PORT / SHUTDOWN_PORT / ENABLE_PORT: HIGH
        - Operacoes criticas (ex: reload): CRITICAL
        """
        highest_risk = "low"
        
        for op in operations:
            intent = op.get("intent")
            
            if intent in (OperationType.CREATE_VLAN.value, OperationType.DELETE_VLAN.value):
                op_risk = "low"
            elif intent in (OperationType.ADD_VLAN_TO_TRUNK.value, OperationType.REMOVE_VLAN_FROM_TRUNK.value):
                op_risk = "medium"
            elif intent in (OperationType.CONFIGURE_ACCESS_PORT.value, OperationType.SHUTDOWN_PORT.value, OperationType.ENABLE_PORT.value):
                op_risk = "high"
            else:
                op_risk = "low"
                
            # Keep highest risk rank: low < medium < high < critical
            if op_risk == "high":
                highest_risk = "high"
            elif op_risk == "medium" and highest_risk == "low":
                highest_risk = "medium"
                
        return highest_risk
