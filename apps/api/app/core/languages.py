"""Supported conversation languages — the single source of truth for language codes.

Every BE site that needs a language code (supervisor default, SSE event defaults,
panel localization, catalog translations) imports from here instead of spelling
``"en"`` / ``"vi"`` inline. The tuple is parity-tested against the FE
``locales`` array in ``apps/web/src/i18n/config.ts`` so the two lists cannot drift.
"""

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
    """Return a supported language code for ``code``, else ``DEFAULT_LANGUAGE``.

    :param code: A raw code (any case, surrounding whitespace, ``None`` or empty).
    :return: The matching entry of ``SUPPORTED_LANGUAGES``, or the default.
    """
    if not code:
        return DEFAULT_LANGUAGE
    cleaned = code.strip().lower()
    return cleaned if cleaned in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
