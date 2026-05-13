"""
AES-256-GCM symmetric encryption with Argon2id key derivation.
Each chunk encrypted individually with a unique 12-byte nonce.
"""
import os
import struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2.low_level import hash_secret_raw, Type
from config import settings


def derive_key(password: str, salt: bytes) -> bytes:
    """Argon2id KDF: password + salt → 32-byte AES key."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
        hash_len=settings.ARGON2_HASH_LEN,
        type=Type.ID,
    )


def generate_salt() -> bytes:
    return os.urandom(settings.ARGON2_SALT_LEN)


def encrypt_bytes(key: bytes, plaintext: bytes, aad: bytes | None = None) -> tuple[bytes, bytes]:
    """
    Returns (nonce, ciphertext+tag).
    nonce: 12 bytes (96-bit, NIST recommended for GCM)
    ciphertext includes 16-byte GCM authentication tag.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_bytes(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None) -> bytes:
    """Decrypt and authenticate. Raises InvalidTag on tampering."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)


def encrypt_file(key: bytes, path: str) -> bytes:
    """Read file from disk, return encrypted blob (nonce || ciphertext)."""
    with open(path, "rb") as f:
        data = f.read()
    nonce, ct = encrypt_bytes(key, data)
    return nonce + ct


def decrypt_to_file(key: bytes, blob: bytes, path: str) -> None:
    """Decrypt blob (nonce || ciphertext) and write to path."""
    nonce, ct = blob[:12], blob[12:]
    data = decrypt_bytes(key, nonce, ct)
    with open(path, "wb") as f:
        f.write(data)