from cryptography.fernet import Fernet, InvalidToken

from hub.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().integration_encryption_key
    if not key:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is required for integrations")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must be a Fernet key") from error


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt(value: bytes) -> str:
    try:
        return _fernet().decrypt(value).decode("utf-8")
    except InvalidToken as error:
        raise RuntimeError("Stored integration credentials could not be decrypted") from error
