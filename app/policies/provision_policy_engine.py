import re
from typing import Dict, Any
from app.models.provision_policy import PolicyViolation, PolicyWarning, PolicyValidationResult

class ProvisionPolicyEngine:
    """
    Policy Engine: Enforces corporate governance, naming conventions, security guidelines,
    inventory rules, and ownership tagging before plan generation.
    """

    RECOMMENDED_PREFIXES = {
        "NETWORK_SWITCH": "sw-",
        "ROUTER_CISCO": "rt-",
        "FIREWALL_SOPHOS": "fw-",
        "SERVER_LINUX": "srv-",
        "VM_PROXMOX": "vm-"
    }

    FORBIDDEN_SNMP_COMMUNITIES = ["public", "private", "123456", "admin"]

    @classmethod
    def evaluate_policies(cls, input_data: Dict[str, Any], profile_name: str) -> PolicyValidationResult:
        hostname = (input_data.get('hostname') or "").strip().lower()
        ip_address = (input_data.get('ip') or "").strip()
        site_name = (input_data.get('site') or "").strip()
        snmp_community = (input_data.get('snmp_community') or "").strip()
        profile_upper = profile_name.upper()

        violations = []
        warnings = []

        # 1. NAMING POLICY
        prefix = cls.RECOMMENDED_PREFIXES.get(profile_upper)
        if prefix and not hostname.startswith(prefix):
            warnings.append(PolicyWarning(
                policy_name="NamingPolicy",
                rule="RECOMMENDED_HOSTNAME_PREFIX",
                message=f"O hostname '{hostname}' não inicia com o prefixo recomendado '{prefix}' para o perfil {profile_upper}."
            ))

        if not re.match(r'^[a-z0-9\-\.]+$', hostname):
            violations.append(PolicyViolation(
                policy_name="NamingPolicy",
                rule="INVALID_HOSTNAME_CHARACTERS",
                message=f"O hostname '{hostname}' contém caracteres inválidos. Utilize apenas letras minúsculas, números, hífens e pontos.",
                severity="HIGH"
            ))

        # 2. SECURITY POLICY
        if snmp_community.lower() in cls.FORBIDDEN_SNMP_COMMUNITIES:
            warnings.append(PolicyWarning(
                policy_name="SecurityPolicy",
                rule="WEAK_SNMP_COMMUNITY",
                message=f"A comunidade SNMP '{snmp_community}' é considerada fraca/padrão. Recomenda-se utilizar uma string complexa."
            ))

        # 3. INVENTORY POLICY
        if not site_name:
            violations.append(PolicyViolation(
                policy_name="InventoryPolicy",
                rule="MANDATORY_SITE",
                message="O campo Site/Localidade é obrigatório pela política de inventário corporativa.",
                severity="CRITICAL"
            ))

        # 4. OWNERSHIP TAGGING POLICY
        tags = {
            "ManagedBy": "NetLens",
            "Profile": profile_upper,
            "Governance": "Enforced"
        }

        passed = len(violations) == 0
        return PolicyValidationResult(passed=passed, violations=violations, warnings=warnings, tags=tags)
