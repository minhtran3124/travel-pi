"""Friendly short codes derived deterministically from resource IDs.

Real IDs are UUIDs — machine-readable but ugly to quote in a chat message
or read aloud. Airlines and hotels solve this with a short alphanumeric
*record locator* (PNR / confirmation number); we use the same trick for
bookings, hotels, and places so an LLM agent or a user can refer to a
resource by something like ``HTL-AB23XY`` instead of a 36-char UUID.

The codes are *derived* (sha256 hash of the ID, base-31 encoded into a
reduced alphabet) so they need no extra storage and never drift: the same
ID always produces the same code.
"""

import hashlib

# Uppercase letters + digits, minus the visually ambiguous ones (0/O,
# 1/I/L) — the same alphabet real airlines/hotels use to keep a reference
# readable when typed or read aloud.
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
