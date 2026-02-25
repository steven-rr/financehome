from cryptography.fernet import Fernet

from app.config import settings


def get_fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode())


def encrypt_token(token: str) -> str:
    f = get_fernet()
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    f = get_fernet()
    return f.decrypt(encrypted_token.encode()).decode()
