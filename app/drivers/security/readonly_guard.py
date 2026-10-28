from app.models.constants import Platform
from app.drivers.security.command_policy import CommandPolicy
from app.drivers.errors import ValidationError

class ReadOnlyCommandGuard:
    _bypass = False

    @staticmethod
    def validate_command(platform: Platform, command: str) -> None:
        if ReadOnlyCommandGuard._bypass:
            return
        if not CommandPolicy.is_allowed(platform, command):
            raise ValidationError(f"Comando REJEITADO pelo Guardiao Read-Only: '{command}'. Este comando nao esta no allowlist da plataforma {platform.value}.")

def bypass_guard(func):
    def wrapper(*args, **kwargs):
        ReadOnlyCommandGuard._bypass = True
        try:
            return func(*args, **kwargs)
        finally:
            ReadOnlyCommandGuard._bypass = False
    return wrapper

from typing import Optional

class ProtectedBaselineGuard:
    _current_transaction: Optional[str] = None

    @classmethod
    def set_transaction(cls, tx_id: Optional[str]) -> None:
        cls._current_transaction = tx_id

    @classmethod
    def get_transaction(cls) -> Optional[str]:
        return cls._current_transaction

    @classmethod
    def validate_command(cls, command: str) -> None:
        cmd_clean = " ".join(command.strip().lower().split())
        tokens = cmd_clean.split()
        
        # If it's baseline initialization, we allow baseline setup commands.
        if cls._current_transaction == "TX-BASELINE-INIT":
            return

        is_violation = False
        
        # 1. Prohibited commands list (from the request)
        blocked_commands = [
            "undo vlan 4092",
            "undo port trunk permit vlan 4092",
            "undo port trunk pvid vlan",
            "port link-type access",
            "port access vlan 11"
        ]
        if any(bc in cmd_clean for bc in blocked_commands):
            is_violation = True
            
        # 2. General baseline protection rules
        else:
            # Check if command is undo/no/delete of vlan 1 or 4092
            if any(x in tokens for x in ("undo", "no", "delete")) and "vlan" in tokens:
                try:
                    vidx = tokens.index("vlan")
                    if vidx + 1 < len(tokens) and tokens[vidx + 1] in ("1", "4092"):
                        is_violation = True
                except ValueError:
                    pass
            
            # Removing PVID 4092/1
            if "pvid" in tokens and any(x in tokens for x in ("undo", "no", "delete")):
                is_violation = True
                
            # Changing link-type on port 24
            if "link-type" in tokens and any(x in tokens for x in ("access", "hybrid", "undo", "no")):
                is_violation = True
                
            if "port" in tokens and "access" in tokens and "vlan" in tokens:
                is_violation = True
                
            # Trunk reconstruction check (multiple VLANs allowed in trunk permit, or touching 4092/1)
            if "permit" in tokens and "vlan" in tokens:
                # If they try to undo permit of vlan 4092 or 1
                if any(x in tokens for x in ("undo", "no")):
                    try:
                        vidx = tokens.index("vlan")
                        if vidx + 1 < len(tokens) and tokens[vidx + 1] in ("1", "4092"):
                            is_violation = True
                    except ValueError:
                        pass
                else:
                    # Check for multiple VLANs in a single permit command (trunk reconstruction)
                    try:
                        vidx = tokens.index("vlan")
                        vlan_tokens = tokens[vidx + 1:]
                        # Filter numeric or range tokens
                        numeric_tokens = [t for t in vlan_tokens if t.isdigit() or "-" in t or "to" in t]
                        if len(numeric_tokens) > 1 or "4092" in numeric_tokens or "1" in numeric_tokens:
                            is_violation = True
                    except ValueError:
                        pass

        if is_violation:
            tx_str = cls._current_transaction or "TX-UNKNOWN"
            raise ValidationError(
                f"PROTECTED_BASELINE_VIOLATION\n"
                f"Operation: {command}\n"
                f"Ownership: BASELINE\n"
                f"Transaction: {tx_str}\n"
                f"Physical execution: NO\n"
                f"Result: BLOCKED"
            )
