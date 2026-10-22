"""Friendly short codes derived deterministically (sha256 → reduced alphabet) from resource IDs, so a resource can be quoted as e.g. ``HTL-AB23XY`` instead of a 36-char UUID."""

import hashlib

# Uppercase letters + digits minus visually ambiguous ones (0/O, 1/I/L).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def short_code_for(resource_id: str) -> str:
    """Derive a stable 6-char code from any resource ID (UUID, slug, …)."""
    digest = hashlib.sha256(resource_id.encode()).digest()
    number = int.from_bytes(digest[:8], "big")
    chars = []
    for _ in range(CODE_LENGTH):
        number, index = divmod(number, len(CODE_ALPHABET))
        chars.append(CODE_ALPHABET[index])
    return "".join(chars)


def prefixed_code(prefix: str, resource_id: str) -> str:
    """Return ``<PREFIX>-XXXXXX`` for ``resource_id``, e.g. 'HTL-AB23XY'."""
    return f"{prefix}-{short_code_for(resource_id)}"
