"""Cryptographic and authentication security primitives for Pressure Out (Phase 3).

Provides:
- Scrypt memory-hard password hashing (`hashlib.scrypt`) with 16-byte random salt
  and constant-time `hmac.compare_digest` verification.
- Password complexity and common breached-password checks.
- HMAC-SHA256 email normalization & hashing for zero-plaintext lookup.
- AES-256-GCM authenticated encryption for optional recovery emails.
- Backup account recovery code generation and verification.
- Cryptographically random session token & CSRF secret generation.
- Privacy-preserving IP subnet hashing (`ip_subnet_hash`).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import AppError

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32

_COMMON_BREACHED_PASSWORDS: frozenset[str] = frozenset(
    {
        "password123",
        "password1234",
        "1234567890",
        "qwertyuiop",
        "letmein1234",
        "admin12345",
        "welcome123",
        "pressureout",
        "iloveyou123",
        "monkey12345",
    }
)


def validate_password_strength(password: str) -> None:
    """Enforce minimum password security requirements."""
    if not isinstance(password, str) or len(password) < 10:
        raise AppError(
            code="WEAK_PASSWORD",
            message="Password must be at least 10 characters long.",
            status_code=422,
        )
    if len(password) > 128:
        raise AppError(
            code="WEAK_PASSWORD",
            message="Password must not exceed 128 characters.",
            status_code=422,
        )
    if not password.strip():
        raise AppError(
            code="WEAK_PASSWORD",
            message="Password cannot consist solely of whitespace.",
            status_code=422,
        )
    if password.strip().lower() in _COMMON_BREACHED_PASSWORDS:
        raise AppError(
            code="WEAK_PASSWORD",
            message="This password appears in common breached password lists. Please choose a stronger passphrase.",
            status_code=422,
        )


def hash_password(password: str) -> str:
    """Hash a password using memory-hard Scrypt with a 128-bit random salt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored Scrypt hash in constant time."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = bytes.fromhex(parts[4])
        expected_dk = bytes.fromhex(parts[5])
        candidate_dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(candidate_dk, expected_dk)
    except Exception:
        return False


def normalize_email(email: str) -> str:
    """Normalize an email address for deterministic hashing and encryption."""
    cleaned = email.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise AppError(
            code="INVALID_EMAIL",
            message="Please provide a valid recovery email address or leave the field blank.",
            status_code=422,
        )
    local_part, domain_part = cleaned.rsplit("@", 1)
    if not local_part or "." not in domain_part or len(cleaned) > 254:
        raise AppError(
            code="INVALID_EMAIL",
            message="Please provide a valid recovery email address or leave the field blank.",
            status_code=422,
        )
    return cleaned


def hash_email_for_lookup(email: str, pepper: str) -> str:
    """Compute HMAC-SHA256 of normalized email so plaintext email is never indexed."""
    norm = normalize_email(email)
    return hmac.new(pepper.encode("utf-8"), norm.encode("utf-8"), hashlib.sha256).hexdigest()


def _decode_aes_key(key_b64: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(key_b64.encode("ascii"))
        if len(raw) == 32:
            return raw
    except Exception:
        pass
    return hashlib.sha256(key_b64.encode("utf-8")).digest()


def encrypt_recovery_email(email: str, key_b64: str) -> bytes:
    """Encrypt normalized recovery email with AES-256-GCM (12-byte random nonce + ciphertext)."""
    norm = normalize_email(email)
    aesgcm = AESGCM(_decode_aes_key(key_b64))
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, norm.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_recovery_email(encrypted_blob: bytes, key_b64: str) -> str:
    """Decrypt an AES-256-GCM encrypted recovery email."""
    if not encrypted_blob or len(encrypted_blob) <= 12:
        raise ValueError("Invalid encrypted email blob.")
    aesgcm = AESGCM(_decode_aes_key(key_b64))
    nonce = encrypted_blob[:12]
    ciphertext = encrypted_blob[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def mask_email_for_owner(email: str) -> str:
    """Mask an email address for display in the owner's private settings (e.g., a***e@e***e.com)."""
    norm = normalize_email(email)
    local, domain = norm.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def generate_backup_recovery_code() -> str:
    """Generate a high-entropy, human-readable one-time recovery code (PO-XXXX-XXXX-XXXX)."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    groups = [
        "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(3)
    ]
    return "PO-" + "-".join(groups)


def hash_session_token(raw_token: str) -> str:
    """Hash a raw session cookie token using SHA-256 before storing or querying in DB."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_session_credentials() -> tuple[str, str, str]:
    """Return `(raw_session_token, token_sha256_hash, csrf_secret)`."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(raw_token)
    csrf_secret = secrets.token_urlsafe(32)
    return raw_token, token_hash, csrf_secret


def verify_csrf_token(expected_csrf_secret: str, provided_header: Optional[str]) -> bool:
    """Verify the `X-CSRF-Token` header against the session's `csrf_secret` in constant time."""
    if not expected_csrf_secret or not provided_header:
        return False
    return hmac.compare_digest(expected_csrf_secret, provided_header.strip())


def hash_ip_subnet(client_ip: Optional[str], pepper: str) -> str:
    """Compute a privacy-preserving HMAC hash of the client IP subnet (/24 IPv4 or /48 IPv6)."""
    if not client_ip:
        return "ip_unknown"
    try:
        addr = ipaddress.ip_address(client_ip.strip())
        if isinstance(addr, ipaddress.IPv4Address):
            net = ipaddress.IPv4Network(f"{addr}/24", strict=False)
            subnet_str = str(net.network_address)
        else:
            net6 = ipaddress.IPv6Network(f"{addr}/48", strict=False)
            subnet_str = str(net6.network_address)
    except ValueError:
        subnet_str = "ip_unparsed"
    return hmac.new(pepper.encode("utf-8"), subnet_str.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
