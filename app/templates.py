"""
Shared Jinja2 templates configuration with i18n support.

Consolidates the 3 duplicate Jinja2Templates instances from:
- app/main.py
- app/routes/videos.py
- app/routes/tags.py

Provides translation loading and helper functions for templates.
"""

import json
from fastapi import Request
from pathlib import Path

from fastapi.templating import Jinja2Templates

# Project root and templates directory
_project_root = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = _project_root / "app" / "templates"

# Translation files directory
TRANSLATIONS_DIR = _project_root / "translations"

# Supported languages and flag mappings
LANG_FLAGS = {
    "en": "🇬🇧",
    "fr": "🇫🇷",
}

# Default language
DEFAULT_LANG = "en"

# Shared Jinja2Templates instance
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Cached translations (loaded once at startup)
_cached_translations: dict[str, dict] = {}


def _load_translation_file(lang: str) -> dict:
    """Load a single translation file. Returns empty dict if not found."""
    file_path = TRANSLATIONS_DIR / f"{lang}.json"
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def get_translations(lang: str | None = None) -> dict:
    """Get translations for the given language with English fallback.

    Returns a merged dict where:
    - English values are the base
    - Target language values override English
    - Missing keys return the key itself (via the _() helper)

    Args:
        lang: Two-letter language code (e.g., "en", "fr"). If None, uses DEFAULT_LANG.

    Returns:
        Dictionary of translations.
    """
    target_lang = lang or DEFAULT_LANG

    # Use cache if available
    if target_lang in _cached_translations:
        return _cached_translations[target_lang]

    # Load English (base) and target language
    en_trans = _load_translation_file("en")
    target_trans = _load_translation_file(target_lang)

    # Merge: English base + target language overrides
    merged = {**en_trans, **target_trans}

    # Cache for future use
    _cached_translations[target_lang] = merged

    return merged


def get_flag(lang: str) -> str:
    """Get the flag emoji for a language code.

    Args:
        lang: Two-letter language code.

    Returns:
        Flag emoji string, or "🌐" if unknown.
    """
    return LANG_FLAGS.get(lang, "🌐")


def make_translator(translations: dict) -> callable:
    """Create a translation function from a translations dict.

    The returned function takes a key and returns:
    - The translated value if found
    - The key itself if not found (debug-friendly)

    Args:
        translations: Dictionary of key -> translated text.

    Returns:
        Function: _(key) -> translated text
    """

    def _(key: str) -> str:
        return translations.get(key, key)

    return _


def get_i18n_context(lang: str) -> dict:
    """Get the full i18n context for template rendering.

    Returns a dict with:
    - _: Translation function
    - current_lang: Two-letter language code
    - current_flag: Flag emoji

    Args:
        lang: Two-letter language code.

    Returns:
        Dictionary for template context.
    """
    translations = get_translations(lang)
    return {
        "_": make_translator(translations),
        "current_lang": lang,
        "current_flag": get_flag(lang),
    }


def get_i18n(request: Request) -> dict:
    """Get i18n context from request.state, with fallback.

    Middleware sets request.state.i18n, but in tests it may not exist.
    """
    return getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))


def parse_accept_language(header: str | None) -> str | None:
    """Parse the Accept-Language header to extract the first language code.

    Example inputs:
        "en-US,en;q=0.9,fr;q=0.8" -> "en"
        "fr-FR,fr;q=0.9" -> "fr"
        None -> None

    Args:
        header: The Accept-Language header value, or None.

    Returns:
        Two-letter language code, or None if header is missing/unparseable.
    """
    if not header:
        return None

    # Split by comma and take first language
    first_lang = header.split(",")[0].strip()

    # Remove quality suffix (e.g., "en-US;q=0.9" -> "en-US")
    if ";" in first_lang:
        first_lang = first_lang.split(";")[0].strip()

    # Extract two-letter code (e.g., "en-US" -> "en")
    if "-" in first_lang:
        first_lang = first_lang.split("-")[0].strip()

    # Only return if it's a valid two-letter code
    if len(first_lang) == 2 and first_lang.isalpha():
        return first_lang.lower()

    return None
