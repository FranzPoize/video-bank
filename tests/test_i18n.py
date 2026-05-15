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
        """No language cookie -> English text in response."""
        response = await client.get("/")
        assert "Video Bank" in response.text  # nav.video_bank in English
        assert "Upload" in response.text       # nav.upload in English

    @pytest.mark.asyncio
    async def test_language_cookie_french(self, client):
        """Cookie: lang=fr -> French text in response."""
        response = await client.get("/", cookies={"lang": "fr"})
        assert "Banque de vidéos" in response.text   # nav.video_bank in French
        assert "Téléverser" in response.text          # nav.upload in French

    @pytest.mark.asyncio
    async def test_accept_language_header(self, client):
        """Accept-Language: fr -> French text in response."""
        response = await client.get(
            "/",
            headers={"accept-language": "fr-FR,fr;q=0.9"},
        )
        assert "Téléverser" in response.text
        assert "Banque de vidéos" in response.text

    @pytest.mark.asyncio
    async def test_invalid_language_fallback(self, client):
        """Invalid lang cookie -> English (default fallback)."""
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
        # SUPPORTED_LANGS = {"en", "fr"}, so "invalid" -> DEFAULT_LANG = "en"
        assert "lang=en" in set_cookie
        assert "Max-Age=2592000" in set_cookie


class TestTranslationSystem:
    """Tests for translation loading, fallback, and missing key behavior.

    These tests call get_translations() and make_translator() directly
    - no HTTP needed. Real JSON files from translations/ are loaded.
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
