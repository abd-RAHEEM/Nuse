import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from hub.config import get_settings

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("nuse-dummy-pin")


def _peppered(pin: str) -> str:
    pepper = get_settings().pin_pepper
    if not pepper:
        raise RuntimeError("PIN_PEPPER is not configured")
    return hmac.new(pepper.encode(), pin.encode(), hashlib.sha256).hexdigest()


def hash_pin(pin: str) -> str:
    return _hasher.hash(_peppered(pin))


def verify_pin(pin: str, pin_hash: str | None) -> bool:
    candidate = _peppered(pin)
    try:
        return _hasher.verify(pin_hash or _DUMMY_HASH, candidate)
    except VerifyMismatchError:
        return False
