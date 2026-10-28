from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class PolicyViolation:
    policy_name: str
    rule: str
    message: str
    severity: str  # "HIGH", "CRITICAL"

@dataclass
class PolicyWarning:
    policy_name: str
    rule: str
    message: str

@dataclass
class PolicyValidationResult:
    passed: bool
    violations: List[PolicyViolation] = field(default_factory=list)
    warnings: List[PolicyWarning] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [{"policy": v.policy_name, "rule": v.rule, "message": v.message, "severity": v.severity} for v in self.violations],
            "warnings": [{"policy": w.policy_name, "rule": w.rule, "message": w.message} for w in self.warnings],
            "tags": self.tags
        }
