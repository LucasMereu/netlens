import logging
import re

class RedactingFormatter(logging.Formatter):
    """
    Formatter that redacts sensitive keys from log messages via SecretSanitizer.
    """
    def format(self, record):
        from app.utils.sanitizer import SecretSanitizer
        msg = super().format(record)
        return SecretSanitizer.sanitize_text(msg)

def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = RedactingFormatter(
            '[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
