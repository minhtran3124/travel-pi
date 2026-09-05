"""app.core.languages — the single source of truth for language codes."""

import re
from pathlib import Path

from app.core.languages import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    normalize,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FE_CONFIG = REPO_ROOT / "apps" / "web" / "src" / "i18n" / "config.ts"


def test_default_is_supported_and_named():
    assert DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES
    assert set(LANGUAGE_NAMES) == set(SUPPORTED_LANGUAGES)


def test_normalize_accepts_supported_codes_any_case_or_padding():
    assert normalize("vi") == "vi"
    assert normalize(" VI ") == "vi"
    assert normalize("en") == "en"


def test_normalize_falls_back_to_default_for_unknown_or_empty():
    assert normalize(None) == DEFAULT_LANGUAGE
    assert normalize("") == DEFAULT_LANGUAGE
    assert normalize("fr") == DEFAULT_LANGUAGE
    assert normalize("vi-VN") == DEFAULT_LANGUAGE


def test_parity_with_frontend_locales():
    src = FE_CONFIG.read_text()
    m = re.search(r"export const locales = \[([^\]]*)\]", src)
    assert m, "apps/web/src/i18n/config.ts must declare `export const locales = [...]`"
    fe = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert fe == SUPPORTED_LANGUAGES
    d = re.search(r'export const defaultLocale: Locale = "([^"]+)"', src)
    assert d and d.group(1) == DEFAULT_LANGUAGE
