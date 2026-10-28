from datetime import datetime
from typing import Dict, Any, Optional
from app.models.canonical_state import CanonicalObservedState
from app.models.reconciliation import ReconciliationDecision
from app.policies.freshness_policy import FreshnessPolicy
from app.services.source_of_truth_service import SourceOfTruthService
from app.drivers.errors import ValidationError

class ReconciliationEngine:
    @staticmethod
    def evaluate_freshness(attribute: str, observed_at_str: str) -> str:
        """
        Retorna 'FRESH' ou 'STALE' baseado na FreshnessPolicy.
        """
        ttl = FreshnessPolicy.get_ttl(attribute)
        now = datetime.utcnow()
        try:
            obs_time = datetime.fromisoformat(observed_at_str.replace("Z", ""))
            age = (now - obs_time).total_seconds()
            return "STALE" if age > ttl else "FRESH"
        except:
            return "STALE"

    @staticmethod
    def reconcile_property(state: CanonicalObservedState, attr_name: str) -> ReconciliationDecision:
        prop = getattr(state, attr_name, None)
        if not prop:
            return ReconciliationDecision(
                decision="BLOCK",
                reason="MISSING_ATTRIBUTE",
                attribute=attr_name,
                authority=SourceOfTruthService.get_authority(attr_name),
                expected=None,
                observed=None,
                confidence="LOW",
                freshness="STALE"
            )
            
        freshness = ReconciliationEngine.evaluate_freshness(attr_name, prop.observed_at)
        
        if freshness == "STALE":
            return ReconciliationDecision(
                decision="BLOCK",
                reason="STALE_DATA",
                attribute=attr_name,
                authority=SourceOfTruthService.get_authority(attr_name),
                expected=None,
                observed=prop.value,
                confidence=prop.confidence,
                freshness="STALE"
            )
            
        if prop.confidence == "CONFLICTING":
            return ReconciliationDecision(
                decision="BLOCK",
                reason="SOURCE_CONFLICT",
                attribute=attr_name,
                authority=SourceOfTruthService.get_authority(attr_name),
                expected=prop.value, # Authoritative value
                observed="DIVERGENT",
                confidence=prop.confidence,
                freshness="FRESH"
            )
            
        return ReconciliationDecision(
            decision="OK",
            reason="CONSISTENT",
            attribute=attr_name,
            authority=SourceOfTruthService.get_authority(attr_name),
            expected=prop.value,
            observed=prop.value,
            confidence=prop.confidence,
            freshness="FRESH"
        )

    @staticmethod
    def reconcile(state: CanonicalObservedState) -> ReconciliationDecision:
        # Check critical properties: hostname, serial, platform
        for attr in ["hostname", "serial", "platform"]:
            decision = ReconciliationEngine.reconcile_property(state, attr)
            if decision.decision == "BLOCK":
                state.status = decision.reason
                return decision
                
        # Availability freshness check
        if state.availability:
            avail_fresh = ReconciliationEngine.evaluate_freshness("zabbix_availability", state.availability.observed_at)
            if avail_fresh == "STALE":
                state.status = "STALE_DATA"
                return ReconciliationDecision(
                    decision="BLOCK",
                    reason="STALE_DATA",
                    attribute="availability",
                    authority="zabbix",
                    expected="UP",
                    observed=state.availability.value,
                    confidence="LOW",
                    freshness="STALE"
                )

        return ReconciliationDecision(
            decision="OK",
            reason="CONSISTENT",
            attribute="all",
            authority="multiple",
            expected=None,
            observed=None,
            confidence="HIGH",
            freshness="FRESH"
        )

    @staticmethod
    def generate_reconciliation_plan(state: CanonicalObservedState) -> None:
        decision = ReconciliationEngine.reconcile(state)
        if decision.decision == "BLOCK":
            raise ValidationError(f"RECONCILIATION_BLOCKED: {decision.reason} on {decision.attribute}.")
        return None
