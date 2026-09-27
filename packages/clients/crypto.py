"""Symmetric encryption for OAuth credentials at rest (Rule.md SS7). The only
module that touches the raw Fernet key — repositories call `encrypt`/`decrypt`,
never construct a Fernet instance themselves (Rule R-3)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from packages.core.exceptions import CredentialNotFoundError


def encrypt(key: str, plaintext: bytes) -> bytes:
    return Fernet(key).encrypt(plaintext)


def decrypt(key: str, ciphertext: bytes) -> bytes:
    try:
        return Fernet(key).decrypt(ciphertext)
    except InvalidToken as exc:
        raise CredentialNotFoundError("Stored credential could not be decrypted") from exc
