from typing import List, Dict, Any, Optional
from app.models.constants import Vendor, OperationType
from app.models.device import DeviceIdentity

class ExpectedState:
    def __init__(self, resource_type: str, resource_id: Any, properties: Dict[str, Any]):
        self.resource_type = resource_type # e.g. "vlan", "interface"
        self.resource_id = resource_id     # e.g. 1008, "TenGigabitEthernet 1/1"
        self.properties = properties       # e.g. {"exists": True, "name": "TEST"}

    def to_dict(self):
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "properties": self.properties
        }

class BeforeState:
    def __init__(self, resource_type: str, resource_id: Any, properties: Dict[str, Any]):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.properties = properties

    def to_dict(self):
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "properties": self.properties
        }

class SemanticOperation:
    def __init__(self, type: OperationType, params: Dict[str, Any]):
        self.type = type
        self.params = params or {}

    def to_dict(self):
        return {
            "type": self.type.value if isinstance(self.type, OperationType) else self.type,
            "params": self.params
        }

class CommandPlan:
    def __init__(self, intent: OperationType, device: DeviceIdentity, commands: List[str], expected_state: ExpectedState, rollback_commands: List[str], before_state: Optional[BeforeState] = None, risk: str = "low", params: Optional[Dict[str, Any]] = None, semantic_operation: Optional[SemanticOperation] = None):
        self.intent = intent
        self.device = device
        self.commands = commands
        self.expected_state = expected_state
        self.rollback_commands = rollback_commands
        self.before_state = before_state
        self.risk = risk
        self.params = params or {}
        self.semantic_operation = semantic_operation

    def to_dict(self):
        return {
            "intent": self.intent.value if isinstance(self.intent, OperationType) else self.intent,
            "device": self.device.to_dict(),
            "commands": self.commands,
            "expected_state": self.expected_state.to_dict() if self.expected_state else None,
            "before_state": self.before_state.to_dict() if self.before_state else None,
            "rollback_commands": self.rollback_commands,
            "risk": self.risk,
            "params": self.params,
            "semantic_operation": self.semantic_operation.to_dict() if self.semantic_operation else None
        }
