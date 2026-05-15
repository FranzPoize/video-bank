# i18n Test Coverage Implementation Plan

**Goal:** Add 12 tests across 3 classes in a new `tests/test_i18n.py` file to cover language detection, language switching, and translation fallback behavior.

**Architecture:** The i18n system consists of JSON translation files (`translations/en.json`, `translations/fr.json`), middleware in `app/main.py` that detects language from cookie/header/default, a `POST /api/lang` endpoint in `app/routes/videos.py` that sets a language cookie, and helper functions in `app/templates.py` (`get_translations()`, `make_translator()`, `parse_accept_language()`). Tests use the existing `client` fixture (httpx.AsyncClient via ASGITransport) for route tests and direct function imports for translation unit tests.

**Design:** `thoughts/shared/designs/2026-05-15-i18n-tests-design.md`

**Key Decisions:**
- Design requires 12 tests across 3 classes. I'm implementing exactly 4+4+4 as specified.
- Translation system tests import `get_translations` and `make_translator` directly from `app.templates` — no mocking, real JSON files are tested.
- Language detection tests go through the full middleware stack via `client` fixture.
- The `test_switch_language` test validates both `set-cookie` header content (`lang=fr`) and cookie attributes (`Max-Age=2592000`).
- No new fixtures needed — `client` from `conftest.py` is sufficient.
- The `_cached_translations` cache in `app.templates` persists across tests within a session but always returns correct data regardless.
- Commit style follows existing convention: `feat(scope): message`.

---

## Dependency Graph

All 12 tests live in a single file with no inter-file dependencies, so this is a single-batch plan.

```
Batch 1 (parallel): ONE file → tests/test_i18n.py (12 tests, 3 classes)
```

---

## Batch 1: Single File (1 implementer)

### Task 1.1: Create `tests/test_i18n.py`
**File:** `tests/test_i18n.py`
**Test:** Embedded in the file itself (all tests are in this file)
**Depends:** none

```python
"""
Tests for i18n: language detection, language switching, and translation fallback.

Run with: pytest tests/test_i18n.py -v

Covers:
- Language detection middleware (cookie, Accept-Language header, defaults, invalid fallback)
- Language switch endpoint POST /api/lang (cookie setting, HTMX/non-HTMX redirect, invalid lang)
- Translation system (loading, French override, missing key fallback, key parity)
"""

import pytest


class TestLanguageDetection:
    """Tests for the language detection middleware.

    The middleware in app/main.py follows this priority:
    1. `lang` cookie (highest priority)
    2. Accept-Language header
    3. Default: "en"
    """

    @pytest.mark.asyncio
    async def test_default_language_english(self, client):
        """No language cookie → English text in response."""
        response = await client.get("/")
        assert "Video Bank" in response.text  # nav.video_bank in English
        assert "Upload" in response.text       # nav.upload in English

    @pytest.mark.asyncio
    async def test_language_cookie_french(self, client):
        """Cookie: lang=fr → French text in response."""
        response = await client.get("/", cookies={"lang": "fr"})
        assert "Banque de vidéos" in response.text   # nav.video_bank in French
        assert "Téléverser" in response.text          # nav.upload in French

    @pytest.mark.asyncio
    async def test_accept_language_header(self, client):
        """Accept-Language: fr → French text in response."""
        response = await client.get(
            "/",
            headers={"accept-language": "fr-FR,fr;q=0.9"},
        )
        assert "Téléverser" in response.text
        assert "Banque de vidéos" in response.text

    @pytest.mark.asyncio
    async def test_invalid_language_fallback(self, client):
        """Invalid lang cookie → English (default fallback)."""
        response = await client.get("/", cookies={"lang": "invalid"})
        # get_translations("invalid") returns English base because
        # _load_translation_file("invalid") returns {} and merge = {**en, **{}}
        assert "Video Bank" in response.text
        assert "Upload" in response.text


class TestLanguageSwitch:
    """Tests for the POST /api/lang language switch endpoint.

    The endpoint sets a 30-day language cookie and redirects
    via HX-Redirect header (HTMX) or 303 (non-HTMX).
    """

    @pytest.mark.asyncio
    async def test_switch_language(self, client):
        """POST /api/lang with valid lang sets language cookie."""
        response = await client.post("/api/lang", json={"lang": "fr"})
        set_cookie = response.headers.get("set-cookie", "")
        assert "lang=fr" in set_cookie
        assert "Max-Age=2592000" in set_cookie  # 30 days
        assert "Path=/" in set_cookie

    @pytest.mark.asyncio
    async def test_switch_language_htmx_redirect(self, client):
        """HTMX request gets HX-Redirect header to Referer."""
        response = await client.post(
            "/api/lang",
            json={"lang": "fr"},
            headers={
                "HX-Request": "true",
                "Referer": "/upload",
            },
        )
        assert response.headers.get("HX-Redirect") == "/upload"

    @pytest.mark.asyncio
    async def test_switch_language_non_htmx_redirect(self, client):
        """Non-HTMX request gets 303 redirect to Referer."""
        response = await client.post(
            "/api/lang",
            json={"lang": "fr"},
            headers={"Referer": "/upload"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/upload"

    @pytest.mark.asyncio
    async def test_switch_invalid_language_fallback(self, client):
        """Invalid language falls back to English, cookie set to 'en'."""
        response = await client.post("/api/lang", json={"lang": "invalid"})
        set_cookie = response.headers.get("set-cookie", "")
        # SUPPORTED_LANGS = {"en", "fr"}, so "invalid" → DEFAULT_LANG = "en"
        assert "lang=en" in set_cookie
        assert "Max-Age=2592000" in set_cookie


class TestTranslationSystem:
    """Tests for translation loading, fallback, and missing key behavior.

    These tests call get_translations() and make_translator() directly
    — no HTTP needed. Real JSON files from translations/ are loaded.
    """

    @pytest.mark.asyncio
    async def test_translation_loading(self):
        """get_translations('en') returns all English translation keys."""
        from app.templates import get_translations

        en = get_translations("en")
        assert en["nav.video_bank"] == "Video Bank"
        assert en["nav.upload"] == "Upload"
        assert en["page.videos"] == "Videos"
        assert len(en) >= 20  # Sanity: English has many keys

    @pytest.mark.asyncio
    async def test_french_translation(self):
        """get_translations('fr') returns French translations."""
        from app.templates import get_translations

        fr = get_translations("fr")
        assert fr["nav.video_bank"] == "Banque de vidéos"
        assert fr["nav.upload"] == "Téléverser"
        assert fr["nav.settings"] == "Paramètres"

    @pytest.mark.asyncio
    async def test_missing_key_fallback(self):
        """Missing translation key returns the key itself (debug-friendly)."""
        from app.templates import get_translations, make_translator

        en = get_translations("en")
        _ = make_translator(en)
        # A key that doesn't exist in any translation file
        assert _("nonexistent.key") == "nonexistent.key"
        assert _("") == ""

    @pytest.mark.asyncio
    async def test_french_missing_key_falls_back_to_english(self):
        """Every key in English translations also exists in French translations.

        This tests the merge behavior: get_translations("fr") merges
        English base + French overrides, so all English keys must be present.
        """
        from app.templates import get_translations

        en = get_translations("en")
        fr = get_translations("fr")

        # Every English key should have a value in French (either the French
        # translation or the English fallback from the merge)
        for key in en:
            assert key in fr, f"FR translation missing key: {key}"
            assert fr[key] is not None

        # Spot-check that French overrides are actually taking effect
        assert fr["nav.video_bank"] == "Banque de vidéos"
```

**Verify:**
```bash
# Run new tests only
pytest tests/test_i18n.py -v

# Run full suite (all 75 existing + 12 new = 87 must pass)
pytest -q

# Expected output (12 tests):
# tests/test_i18n.py::TestLanguageDetection::test_default_language_english PASSED
# tests/test_i18n.py::TestLanguageDetection::test_language_cookie_french PASSED
# tests/test_i18n.py::TestLanguageDetection::test_accept_language_header PASSED
# tests/test_i18n.py::TestLanguageDetection::test_invalid_language_fallback PASSED
# tests/test_i18n.py::TestLanguageSwitch::test_switch_language PASSED
# tests/test_i18n.py::TestLanguageSwitch::test_switch_language_htmx_redirect PASSED
# tests/test_i18n.py::TestLanguageSwitch::test_switch_language_non_htmx_redirect PASSED
# tests/test_i18n.py::TestLanguageSwitch::test_switch_invalid_language_fallback PASSED
# tests/test_i18n.py::TestTranslationSystem::test_translation_loading PASSED
# tests/test_i18n.py::TestTranslationSystem::test_french_translation PASSED
# tests/test_i18n.py::TestTranslationSystem::test_missing_key_fallback PASSED
# tests/test_i18n.py::TestTranslationSystem::test_french_missing_key_falls_back_to_english PASSED
```

**Commit:** `feat(tests): add i18n test coverage for language detection, switch, and translation fallback`

---

## Verification Steps

After implementing:

1. **Run the new tests only** to verify they pass:
   ```bash
   pytest tests/test_i18n.py -v
   ```

2. **Run the full suite** to verify no regressions (all 87 must pass):
   ```bash
   pytest -q
   ```

3. **Check for any issues:**
   - The `_cached_translations` module-level cache in `app/templates.py` persists across tests but always returns correct data — no issue.
   - The existing test `test_upload_form_page` checks `"Upload" in response.text` — this still works because default language is English.
   - The existing test `test_settings_page_loads` checks for `<html` to avoid i18n dependency — no change needed.

---

## Implementation Notes

**Pre-existing patterns followed:**
- `@pytest.mark.asyncio` on every test method — matches all existing tests
- `client` fixture from `conftest.py` — provides httpx.AsyncClient with ASGITransport
- Classes grouped by concern with docstrings — matches `test_videos.py`, `test_tags.py`, etc.
- Docstrings on every test method — matches existing convention
- Direct imports inside test methods for translation tests — matches `TestTagServiceFunctions` pattern
- No new dependencies — all tests use `pytest` + existing fixtures
- No application code changes — tests only
