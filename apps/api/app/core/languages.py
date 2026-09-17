"""Supported conversation languages — the single source of truth for language codes, parity-tested against the FE ``locales`` array so the two cannot drift."""

from __future__ import annotations

from typing import Literal

Language = Literal["en", "vi"]

#: ISO-639-1 codes the app understands, in FE ``locales`` order.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "vi")

#: Source language of all seeded catalog text and the fallback for unknown codes.
DEFAULT_LANGUAGE: str = "en"

#: Human-readable names, used when a prompt must name the target language.
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "vi": "Vietnamese"}


def normalize(code: str | None) -> str:
    """Return a supported language code for ``code``, else ``DEFAULT_LANGUAGE``."""
    if not code:
        return DEFAULT_LANGUAGE
    cleaned = code.strip().lower()
    return cleaned if cleaned in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
