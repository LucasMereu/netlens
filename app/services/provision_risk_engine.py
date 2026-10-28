from typing import Dict, Any, List
from app.models.provision_risk import RiskLevel, RiskAssessment
from app.models.provision_policy import PolicyValidationResult
from app.models.provision_dependency import DependencyStatus, DependencyResult

class ProvisionRiskEngine:
    """
    Risk Engine (Sprint 10.7.8):
    Evaluates profile, policies, dependencies, and drift to assign deterministic
    Risk Level (LOW, MEDIUM, HIGH, CRITICAL) and Risk Score (0-100).
    CRITICAL risk level automatically sets can_apply = False to BLOCK APPLY.
    """

    @classmethod
    def assess_risk(
        cls,
        input_data: Dict[str, Any],
        profile_name: str,
        policy_result: PolicyValidationResult,
        discovery_results: Dict[str, DependencyResult]
    ) -> RiskAssessment:
        score = 0
        risk_factors = []
        profile_upper = profile_name.upper()

        # 1. PROFILE BASE RISK
        if profile_upper in ("ROUTER_CISCO", "FIREWALL_SOPHOS"):
            score += 30
            risk_factors.append(f"Perfil de infraestrutura crítica ({profile_upper}) (+30 score).")
        elif profile_upper == "SERVER_LINUX":
            score += 15
            risk_factors.append("Perfil de servidor físico (+15 score).")
        else:
            score += 10
            risk_factors.append(f"Perfil padrão {profile_upper} (+10 score).")

        # 2. POLICY WARNINGS & SECURITY RISK
        for warning in policy_result.warnings:
            if warning.rule == "WEAK_SNMP_COMMUNITY":
                score += 50
                risk_factors.append(f"Alerta de Segurança: Comunidade SNMP fraca ({warning.message}) (+50 score).")
            else:
                score += 15
                risk_factors.append(f"Aviso de Política: {warning.message} (+15 score).")

        # 3. DEPENDENCY & CONFLICT RISK
        has_conflict = False
        has_unknown = False

        for sys_name, res in discovery_results.items():
            if res.status == DependencyStatus.CONFLICT:
                score += 60
                has_conflict = True
                risk_factors.append(f"Conflito no sistema {sys_name.upper()}: {'; '.join(res.conflicts)} (+60 score).")
            elif res.status == DependencyStatus.UNKNOWN:
                score += 50
                has_unknown = True
                risk_factors.append(f"Estado desconhecido/indisponível no sistema {sys_name.upper()} (+50 score).")
            elif res.status == DependencyStatus.STALE:
                score += 30
                risk_factors.append(f"Dados desatualizados (STALE) no sistema {sys_name.upper()} (+30 score).")

        # Cap score at 100
        score = min(100, score)

        # 4. DETERMINE RISK LEVEL & CAN_APPLY GATE
        requires_elevated = False
        can_apply = True

        if score >= 81 or has_conflict or has_unknown:
            level = RiskLevel.CRITICAL
            can_apply = False
            risk_factors.append("BLOQUEIO AUTOMÁTICO: Nível Risco CRÍTICO ou Conflito detectado (APPLY BLOCKED).")
        elif score >= 56:
            level = RiskLevel.HIGH
            requires_elevated = True
            risk_factors.append("Requer aprovação com elevação de privilégio devido ao Risco ALTO.")
        elif score >= 26:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return RiskAssessment(
            risk_level=level,
            risk_score=score,
            risk_factors=risk_factors,
            requires_elevated_approval=requires_elevated,
            can_apply=can_apply
        )
