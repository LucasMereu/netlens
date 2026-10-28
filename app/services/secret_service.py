import os
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.utils.logging import get_logger

logger = get_logger("secret_service")

class ConfigurationError(Exception):
    """Raised when critical configuration like NETLENS_MASTER_KEY is missing."""
    pass

class SecretService:
    _fernet_instance: Optional[Fernet] = None
    _current_raw_key: Optional[str] = None

    @classmethod
    def get_fernet(cls) -> Fernet:
        """
        Retrieves or initializes Fernet instance using NETLENS_MASTER_KEY environment variable.
        STRICT MANDATE: NO SILENT FALLBACK KEY GENERATION.
        If NETLENS_MASTER_KEY is missing, raises ConfigurationError to prevent overwriting existing plans.
        """
        raw_key = os.environ.get("NETLENS_MASTER_KEY", "").strip()
        if not raw_key:
            cls._fernet_instance = None
            cls._current_raw_key = None
            raise ConfigurationError(
                "CONFIG_ERROR: A variável de ambiente NETLENS_MASTER_KEY é obrigatória para criptografia de segredos em repouso. "
                "Operação abortada para impedir corrupção/sobrescrita de planos."
            )

        if cls._fernet_instance is not None and cls._current_raw_key == raw_key:
            return cls._fernet_instance

        try:
            key_bytes = raw_key.encode("utf-8")
            if len(key_bytes) != 44:
                padded = base64.urlsafe_b64encode(raw_key.zfill(32)[:32].encode("utf-8"))
                cls._fernet_instance = Fernet(padded)
            else:
                cls._fernet_instance = Fernet(key_bytes)
            cls._current_raw_key = raw_key
            return cls._fernet_instance
        except Exception as e:
            cls._fernet_instance = None
            cls._current_raw_key = None
            raise ConfigurationError(f"CONFIG_ERROR: Falha ao inicializar chave criptográfica Fernet: {e}")

    @classmethod
    def encrypt_secret(cls, secret_str: str) -> str:
        """
        Encrypts a raw secret string into FERNET:<token> format.
        """
        if not secret_str:
            return ""
        if secret_str.startswith("FERNET:"):
            return secret_str

        fernet = cls.get_fernet()
        token = fernet.encrypt(secret_str.encode("utf-8")).decode("utf-8")
        return f"FERNET:{token}"

    @classmethod
    def decrypt_secret(cls, enc_str: str) -> str:
        """
        Decrypts FERNET:<token> or legacy ENC:<base64> (READ-ONLY migration mode).
        Returns decrypted raw secret string.
        """
        if not enc_str:
            return ""

        # Legacy ENC:<base64> READ-ONLY migration handling
        if enc_str.startswith("ENC:"):
            try:
                logger.warning("MIGRAÇÃO DE SEGREDOS: Decodificando formato legado ENC:<base64>. O segredo será re-persistido como FERNET:<token> no próximo save.")
                return base64.b64decode(enc_str[4:].encode("utf-8")).decode("utf-8")
            except Exception as e:
                logger.error(f"Erro ao decodificar segredo legado ENC: {e}")
                return ""

        if enc_str.startswith("FERNET:"):
            token = enc_str[7:]
            fernet = cls.get_fernet()
            try:
                return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except InvalidToken:
                logger.error("Token Fernet inválido ou chave NETLENS_MASTER_KEY incorreta.")
                raise ConfigurationError("DECRYPTION_ERROR: Falha ao descriptografar segredo. Verifique se a NETLENS_MASTER_KEY está correta.")
            except Exception as e:
                logger.error(f"Erro na descriptografia Fernet: {e}")
                return ""

        # Unencrypted raw string return
        return enc_str
