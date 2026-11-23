from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from poc_toolbox.config import AIEncryptionSettings


def _load_cipher() -> Fernet:
    try:
        master_key = AIEncryptionSettings().encryption_key.get_secret_value()
    except ValidationError:
        raise ValueError('AI_CONFIG_ENCRYPTION_KEY is required') from None
    if not master_key:
        raise ValueError('AI_CONFIG_ENCRYPTION_KEY is required')
    try:
        return Fernet(master_key.encode('ascii'))
    except (ValueError, UnicodeError):
        raise ValueError('AI_CONFIG_ENCRYPTION_KEY must be a valid Fernet key') from None


def encrypt_api_key(api_key: str) -> str:
    return _load_cipher().encrypt(api_key.encode('utf-8')).decode('ascii')


def decrypt_api_key(api_key_ciphertext: str) -> str:
    cipher = _load_cipher()
    try:
        return cipher.decrypt(api_key_ciphertext.encode('ascii')).decode('utf-8')
    except (InvalidToken, UnicodeError):
        raise ValueError('Unable to decrypt API key') from None
