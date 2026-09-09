"""
PMI中国AI项目管理社区 - 字段级加密模块
支持数据库字段的AES-256-GCM加密/解密
"""

import os
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


# 从环境变量获取加密密钥，如果没有则使用SECRET_KEY派生
_ENCRYPTION_KEY: Optional[bytes] = None
_SALT = b"tw-ai-pms-compliance-salt-v1"


def _get_encryption_key() -> bytes:
    """获取或派生加密密钥"""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    env_key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if env_key:
        key_bytes = base64.urlsafe_b64decode(env_key)
        if len(key_bytes) == 32:
            _ENCRYPTION_KEY = key_bytes
            return _ENCRYPTION_KEY

    # 使用 PBKDF2 从 SECRET_KEY 派生 256-bit 密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100000,
    )
    key = kdf.derive(settings.SECRET_KEY.encode("utf-8"))
    _ENCRYPTION_KEY = key
    return key


def encrypt_field(plaintext: str) -> str:
    """
    加密字段值

    Args:
        plaintext: 明文数据

    Returns:
        base64编码的密文（包含nonce和tag）
    """
    if not plaintext:
        return plaintext

    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    combined = nonce + ciphertext
    return base64.urlsafe_b64encode(combined).decode("utf-8")


def decrypt_field(ciphertext: str) -> str:
    """
    解密字段值

    Args:
        ciphertext: base64编码的密文

    Returns:
        明文数据
    """
    if not ciphertext:
        return ciphertext

    try:
        key = _get_encryption_key()
        aesgcm = AESGCM(key)
        combined = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        nonce = combined[:12]
        encrypted_data = combined[12:]
        plaintext = aesgcm.decrypt(nonce, encrypted_data, None)
        return plaintext.decode("utf-8")
    except Exception:
        # 如果解密失败，可能是明文存储的旧数据，直接返回
        return ciphertext


def generate_field_encryption_key() -> str:
    """
    生成新的字段加密密钥

    Returns:
        base64编码的32字节密钥
    """
    key = os.urandom(32)
    return base64.urlsafe_b64encode(key).decode("utf-8")


class EncryptedField:
    """
    SQLAlchemy 类型装饰器风格的加密字段辅助类
    用于在应用层对字段进行加解密
    """

    def __init__(self, value: Optional[str] = None):
        self._encrypted_value: Optional[str] = None
        self._plaintext: Optional[str] = None
        if value is not None:
            self.plaintext = value

    @property
    def plaintext(self) -> Optional[str]:
        if self._plaintext is not None:
            return self._plaintext
        if self._encrypted_value is not None:
            self._plaintext = decrypt_field(self._encrypted_value)
            return self._plaintext
        return None

    @plaintext.setter
    def plaintext(self, value: str):
        self._plaintext = value
        self._encrypted_value = encrypt_field(value)

    @property
    def encrypted(self) -> Optional[str]:
        if self._encrypted_value is not None:
            return self._encrypted_value
        if self._plaintext is not None:
            self._encrypted_value = encrypt_field(self._plaintext)
            return self._encrypted_value
        return None

    def __str__(self):
        return self.plaintext or ""

    def __repr__(self):
        return f"EncryptedField(plaintext={'***' if self._plaintext else None})"
