import re
import copy
from typing import Any, Dict, List, Union

class SecretSanitizer:
    """
    Centralized Structural & Textual Secret Sanitizer.
    Scrubs passwords, communities, tokens, Authorization headers, and secret keys
    from text strings, dictionaries, lists, and exceptions without mutating original inputs.
    """

    REDACT_PATTERNS = [
        r'(?i)(snmp_community["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(community["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(password_hash["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(sshpass\s+-p\s+["\']?)([^"\'\s]+)(["\']?)',
        r'(?i)(api_token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(secret_key["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(Authorization["\']?\s*[:=]\s*["\']?Bearer\s+)([^"\'\s]+)(["\']?)',
        r'(?i)(X-Auth-Token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
        r'(?i)(token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])'
    ]

    SENSITIVE_KEYS = {
        'snmp_community', 'community', 'password', 'password_hash', 'sshpass',
        'api_token', 'secret_key', 'token', 'auth_token', 'authorization',
        'x-auth-token', '_secret_snmp_community', 'secret'
    }

    _compiled_patterns = [re.compile(p) for p in REDACT_PATTERNS]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Textual scrubbing for logs, exception tracebacks, and raw HTTP outputs."""
        if not text or not isinstance(text, str):
            return text
        sanitized = text
        for pattern in cls._compiled_patterns:
            sanitized = pattern.sub(r'\1[REDACTED]\3', sanitized)
        return sanitized

    @classmethod
    def sanitize_dict(cls, data: Union[Dict, List, Any]) -> Union[Dict, List, Any]:
        """
        Deep recursive dictionary and list scrubbing.
        Returns a sanitized copy without mutating the original input object.
        """
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(k, str) and k.lower() in cls.SENSITIVE_KEYS:
                    cleaned[k] = "[REDACTED]"
                else:
                    cleaned[k] = cls.sanitize_dict(v)
            return cleaned
        elif isinstance(data, list):
            return [cls.sanitize_dict(item) for item in data]
        elif isinstance(data, str):
            return cls.sanitize_text(data)
        else:
            return data

    @classmethod
    def sanitize_exception(cls, exc: Exception) -> str:
        """Converts exception to string and applies full textual redaction."""
        if not exc:
            return ""
        raw_msg = str(exc)
        return cls.sanitize_text(raw_msg)
