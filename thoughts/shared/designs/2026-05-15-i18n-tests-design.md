---
date: 2026-05-15
topic: "i18n Tests — Coverage for language switching and translation behavior"
status: draft
---

## Problem Statement

The i18n system (JSON-based translations, cookie detection, language switch endpoint) has no test coverage. The system works in production, but there are no regression guards for translation loading, language detection, cookie setting, or fallback behavior. The i18n design doc specified 5 test cases that were never implemented.

## Constraints

- Follow existing test patterns: `pytest-asyncio`, `httpx.AsyncClient`, in-memory SQLite
- One new file: `tests/test_i18n.py`
- All 75 existing tests must remain passing
- No new dependencies
- No changes to application code (tests only)

## Approach

Create `tests/test_i18n.py` with three test classes covering:

1. **Language detection middleware** — cookie, header, defaults
2. **Language switch endpoint** — `POST /api/lang`
3. **Translation system** — fallback behavior, missing keys

**I'm keeping this lean.** The i18n system is simple (JSON files + middleware), so testing the documented behaviors is sufficient. No need to test Jinja2 rendering for every template — the existing route tests already verify pages render.

## Architecture

```
tests/test_i18n.py
├── TestLanguageDetection
│   ├── test_default_language_english      — No cookie → English text
│   ├── test_language_cookie_french        — Cookie: lang=fr → French text
│   ├── test_accept_language_header        — Header → detected language
│   └── test_invalid_language_fallback     — Invalid cookie → English
│
├── TestLanguageSwitch
│   ├── test_switch_language               — POST /api/lang sets cookie
│   ├── test_switch_language_redirect      — Sets HX-Redirect or 303
│   └── test_switch_invalid_language       — Invalid code is ignored
│
└── TestTranslationSystem
    ├── test_translation_loading           — get_translations() loads correctly
    ├── test_missing_key_fallback          — Missing key returns key itself
    └── test_french_fallback               — Missing FR key falls back to EN
```

## Components

### 1. TestLanguageDetection

Tests the middleware-driven language detection flow.

**test_default_language_english:**
```python
async def test_default_language_english(self, client):
    """No language cookie → English text in response."""
    response = await client.get("/")
    assert "Video Bank" in response.text  # nav.video_bank in English
    assert "Upload" in response.text       # nav.upload in English
```

**test_language_cookie_french:**
```python
async def test_language_cookie_french(self, client):
    """Cookie: lang=fr → French text in response."""
    response = await client.get("/", cookies={"lang": "fr"})
    assert "Banque de vidéos" in response.text
    assert "Téléverser" in response.text
```

**test_accept_language_header:**
```python
async def test_accept_language_header(self, client):
    """Accept-Language: fr → French text."""
    response = await client.get("/", headers={"accept-language": "fr-FR,fr;q=0.9"})
    assert "Téléverser" in response.text
```

**test_invalid_language_fallback:**
```python
async def test_invalid_language_fallback(self, client):
    """Invalid lang cookie → English (default)."""
    response = await client.get("/", cookies={"lang": "invalid"})
    assert "Video Bank" in response.text
```

### 2. TestLanguageSwitch

Tests the `POST /api/lang` endpoint.

**test_switch_language:**
```python
async def test_switch_language(self, client):
    """POST /api/lang sets language cookie."""
    response = await client.post("/api/lang", json={"lang": "fr"})
    set_cookie = response.headers.get("set-cookie", "")
    assert "lang=fr" in set_cookie
    assert "Max-Age=2592000" in set_cookie
```

**test_switch_language_htmx_redirect:**
```python
async def test_switch_language_htmx_redirect(self, client):
    """HTMX request gets HX-Redirect header."""
    response = await client.post(
        "/api/lang",
        json={"lang": "fr"},
        headers={
            "HX-Request": "true",
            "Referer": "/upload",
        },
    )
    assert response.headers.get("HX-Redirect") == "/upload"
```

**test_switch_language_non_htmx_redirect:**
```python
async def test_switch_language_non_htmx_redirect(self, client):
    """Non-HTMX request gets 303 redirect."""
    response = await client.post(
        "/api/lang",
        json={"lang": "fr"},
        headers={"Referer": "/upload"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/upload"
```

**test_switch_invalid_language:**
```python
async def test_switch_invalid_language(self, client):
    """Invalid language falls back to English, cookie still set."""
    response = await client.post("/api/lang", json={"lang": "invalid"})
    set_cookie = response.headers.get("set-cookie", "")
    assert "lang=en" in set_cookie
```

### 3. TestTranslationSystem

Tests the `get_translations()` function directly (no HTTP needed).

**test_translation_loading:**
```python
async def test_translation_loading(self):
    """get_translations loads the correct keys."""
    from app.templates import get_translations
    en = get_translations("en")
    assert en["nav.video_bank"] == "Video Bank"
    assert en["nav.upload"] == "Upload"
```

**test_french_translation:**
```python
async def test_french_translation(self):
    """French translations override English."""
    from app.templates import get_translations
    fr = get_translations("fr")
    assert fr["nav.video_bank"] == "Banque de vidéos"
    assert fr["nav.upload"] == "Téléverser"
```

**test_missing_key_fallback:**
```python
async def test_missing_key_fallback(self):
    """Missing key returns the key itself (debug-friendly)."""
    from app.templates import get_translations, make_translator
    fr = get_translations("fr")
    _ = make_translator(fr)
    assert _("nonexistent.key") == "nonexistent.key"
```

**test_french_missing_key_falls_back_to_english:**
```python
async def test_french_missing_key_falls_back_to_english(self):
    """FR translation missing a key → English value is used."""
    from app.templates import get_translations
    en = get_translations("en")
    fr = get_translations("fr")
    # Verify FR has all EN keys
    for key in en:
        assert key in fr, f"FR translation missing key: {key}"
```

## Data Flow

### Language Detection Test Flow
```
Test: Request without cookie
  → GET /
  → Middleware: no cookie → check Accept-Language → none → default "en"
  → English values in response HTML
  → Assert "Video Bank" in response.text

Test: Request with Cookie: lang=fr
  → GET / (cookies={"lang": "fr"})
  → Middleware: lang=fr from cookie
  → French values in response HTML
  → Assert "Banque de vidéos" in response.text
```

### Language Switch Test Flow
```
Test: POST /api/lang with {"lang": "fr"}
  → Endpoint sets cookie: lang=fr
  → Returns HX-Redirect (HTMX) or 303 (non-HTMX)
  → Assert set-cookie header contains lang=fr
```

## Error Handling

| Scenario | Expected Behavior | Test |
|----------|------------------|------|
| No language cookie | Default to "en" | `test_default_language_english` |
| Invalid language cookie | Fallback to "en" | `test_invalid_language_fallback` |
| Missing translation key | Return key name | `test_missing_key_fallback` |
| FR missing EN key | Fallback to EN value | `test_french_missing_key_falls_back_to_english` |
| Invalid lang in POST | Fallback to "en", cookie set | `test_switch_invalid_language` |

## Testing Strategy

- **10 new tests** in `tests/test_i18n.py`
- All test via `httpx.AsyncClient` for route tests (3 tests use direct function calls for translation loading)
- No new fixtures needed — existing `client` and `db` fixtures work
- No mocking needed — translations are real JSON files
- Run: `pytest tests/test_i18n.py -v`

## Open Questions

None. The i18n design already specified these tests — this document formalizes them for implementation.

## Implementation Checklist

### Phase 1: Create test file
- [ ] Create `tests/test_i18n.py`
- [ ] Implement `TestLanguageDetection` (4 tests)
- [ ] Implement `TestLanguageSwitch` (4 tests)
- [ ] Implement `TestTranslationSystem` (4 tests)

### Phase 2: Verify
- [ ] Run new tests: `pytest tests/test_i18n.py -v`
- [ ] Run full suite: `pytest -q` (all 85 must pass)
