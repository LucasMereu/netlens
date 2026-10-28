from datetime import datetime
from typing import Optional, List, Dict, Any

class ReconciliationDecision:
    def __init__(self, decision: str, reason: str, attribute: str, authority: str, expected: Any, observed: Any, confidence: str, freshness: str, timestamp: str = ""):
        self.decision = decision # BLOCK, PROPOSE, OK
        self.reason = reason
        self.attribute = attribute
        self.authority = authority
        self.expected = expected
        self.observed = observed
        self.confidence = confidence
        self.freshness = freshness
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "attribute": self.attribute,
            "authority": self.authority,
            "expected": self.expected,
            "observed": self.observed,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "timestamp": self.timestamp
        }
