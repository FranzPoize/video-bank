---
date: 2026-05-18
topic: "Franken UI Rebuild"
status: validated
---

## Problem Statement

The Video Bank UI is built with raw CSS (382-line `style.css`) and extensive inline styles scattered across 18 Jinja2 templates. This is brittle, hard to maintain, and visually inconsistent. We need a professional UI framework that integrates cleanly with the existing Python/FastAPI/Jinja2/HTMX stack without adding a build pipeline.

## Constraints

- **No npm/node build pipeline** — the project currently has no `package.json`, `node_modules/`, or build tooling. Adding one would be disproportionate scope for a server-rendered app.
- **Zero Python backend changes** — all routes, services, database, and middleware remain untouched. This is a pure template/CSS replacement.
- **HTMX compatibility** — `hx-*` attributes must continue working. Franken UI's `uk-*` / `data-uk-*` prefixes don't conflict.
- **i18n** — the existing `_("key")` translation function must keep working in all templates.
- **Vanilla JS** — `upload.js` and `clipper.js` must remain functional.
- **Dark mode** — must work with system preference and allow manual toggle.
- **All 18 templates** must be migrated — no regressions in layout or behavior.

## Approach

**Chosen: CDN Integration (no build step)**

Franken UI provides a fully-featured CDN distribution that includes:
- All CSS components (cards, buttons, forms, tables, nav, badges, etc.)
- All JavaScript behaviors (dropdowns, modals, notifications, theme switching)
- Lucide icon library via `<uk-icon>` web components
- 15 built-in color themes + dark mode
- Responsive utilities

The only thing the CDN approach lacks vs the NPM+Vite route is **custom palette colors** beyond the 15 built-in themes. This is an acceptable trade-off — the built-in themes (Neutral, Zinc, Blue, Green, etc.) cover our needs. We can layer a small custom CSS file later if needed.

**Alternatives considered:**
- **NPM + Vite plugin** — rejected because it requires adding a full JS build pipeline to a Python project. Over-engineered for a server-rendered app with minimal client JS.
- **NPM + Tailwind plugin** — rejected for the same reason, plus it's the older approach with more configuration surface.

## Architecture

### Before and After

**Before:**
```
base.html → links /static/css/style.css (382 lines of custom CSS)
          → inline styles in every template
          → custom language dropdown with vanilla JS toggle
          → custom upload popup with absolute positioning
          → hardcoded colors (#4361ee, #e63946, #1a1a2e, etc.)

After:
base.html → links franken-ui CDN (core.min.css + utilities.min.css)
          → links /static/css/custom.css (~50 lines for clip seeker overrides)
          → Franken UI classes in all templates
          → data-uk-dropdown for language switcher
          → UIkit.notification() for upload feedback
          → CSS variables for theming (--primary, --destructive, etc.)
```

### Theme Configuration

Default theme applied to `<html>` element:
- Theme: `uk-theme-neutral`
- Radii: `uk-radii-md`
- Shadows: `uk-shadows-sm`
- Font: `uk-font-sm`

Persistence via `localStorage` under `__FRANKEN__` key. Dark mode respects `prefers-color-scheme` as fallback.

## Components

### 1. Base Layout (`base.html`)

| Element | Current | Franken UI |
|---------|---------|------------|
| Body | `background: #f5f5f5` | `<body class="bg-background text-foreground">` |
| Nav | `background: #1a1a2e` | `<nav class="bg-background border-b">` with flex layout |
| Container | `max-width: 1200px; margin: 0 auto; padding: 2rem;` | `<main class="uk-container">` |
| Language switcher | Custom JS toggle | `<div data-uk-dropdown="mode: click">` |
| Space indicator | Custom colored spans | `<span class="uk-badge uk-badge-{modifier}">` |
| Upload popup | Fixed-position div | `UIkit.notification()` JS API |
| Theme setup | None | `<script>` block in `<head>` reading localStorage |

### 2. Video Grid (`_video_grid.html`)

| Element | Current | Franken UI |
|---------|---------|------------|
| Card container | Inline styles with `box-shadow` | `<div class="uk-card">` |
| Thumbnail area | `background: #ddd` | `<div class="bg-muted">` |
| Video title | Inline `<h3>` | `<h3 class="uk-card-title">` |
| Tags | Custom styled spans | `<span class="uk-badge uk-badge-primary">` |
| Grid layout | `display: grid; gap: 1.5rem;` | `<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">` |

### 3. Forms (upload, edit, match_form)

| Element | Current | Franken UI |
|---------|---------|------------|
| Form layout | Inline block labels | `uk-form-stacked` |
| Text inputs | `border: 1px solid #ccc; border-radius: 6px;` | `class="uk-input"` |
| Select | Custom styled | `class="uk-select"` |
| Textarea | Inline style | `class="uk-textarea"` |
| File input | Standard input | `<div data-uk-form-custom>` wrapping `<input type="file">` + button |
| Range slider | Standard `<input type="range">` | `class="uk-range"` |
| Labels | `<label style="display: block; ...">` | `<label class="uk-form-label">` |

### 4. Tables (settings, match stats)

| Element | Current | Franken UI |
|---------|---------|------------|
| Tag table | Custom flex-based layout | `<table class="uk-table uk-table-divider">` |
| Stats table | Custom `<table>` with hardcoded colors | `<table class="uk-table uk-table-sm">` |
| Table header | `background: #1a1a2e; color: #fff;` | `<thead class="bg-muted text-muted-foreground">` |

### 5. Buttons

| Variant | Current Class | Franken UI Class |
|---------|--------------|------------------|
| Primary | `btn btn-primary` | `uk-btn uk-btn-primary` |
| Danger | `btn btn-danger` | `uk-btn uk-btn-destructive` |
| Default | `btn btn-inactive` | `uk-btn uk-btn-default` |
| Small | `btn-sm` | `uk-btn-sm` |

### 6. Badges

| Use | Current | Franken UI |
|-----|---------|------------|
| Video tags | `background: #e0e7ff; color: #4361ee; border-radius: 12px;` | `uk-badge uk-badge-primary` |
| Space indicator ok | Custom green span | `uk-badge` (default) |
| Space indicator warn | Custom yellow span | `uk-badge uk-badge-warning` (custom CSS class) |
| Space indicator critical | Custom red span | `uk-badge uk-badge-destructive` |

## Data Flow

No changes to any data flow. This is a **presentation-layer-only** rebuild:

- Templates get new CSS classes — same Jinja2 variables, same HTMX attributes
- Upload progress notification swaps from a managed DOM element to `UIkit.notification()`
- The i18n `_()` function works identically
- HTMX swap targets (`#main-content`, `#video-grid`, `#match-videos-section`) are unaffected
- All `<form>` actions, `hx-post`, `hx-get` URLs stay the same

## Error Handling

| Scenario | Current Behavior | Franken UI Behavior |
|----------|-----------------|---------------------|
| Form validation error | `<div class="error">` | `<div class="uk-alert uk-alert-destructive">` or inline `uk-form-destructive` |
| Upload error | Shown in popup div | `UIkit.notification({status: 'destructive'})` |
| Server error page | Custom styled error | `uk-card` centered with `uk-hero-lg` status code |

## Testing Strategy

- **Visual regression**: Manual review of each page after template migration
- **HTMX behavior**: Verify all `hx-*` attributes still work (filter bar, sort, video linking, space indicator refresh)
- **JS behavior**: Verify `upload.js` and `clipper.js` still function correctly
- **Dark mode**: Test each template in light and dark mode
- **Responsive**: Test mobile layout for each page
- **i18n**: Verify translations render correctly with new template structure
- **Existing test suite**: Run `pytest tests/ -v` — all tests must pass (they test backend behavior, which is unchanged)

## Migration Phases

### Phase 1: Foundation (3 templates)
- `base.html` — head setup, body classes, nav, container, theme system, JS includes
- `_upload_popup.html` — replace with notification API
- `_space_fragment.html` — badge classes

### Phase 2: Video Pages (5 templates)
- `index.html`, `_content.html`, `_video_grid.html`, `video_detail.html`

### Phase 3: Forms (3 templates)
- `upload.html`, `edit.html`, `match_form.html` (partial)

### Phase 4: Match System (5 templates)
- `match_list.html`, `match_detail.html`, `match_form.html` (completion)
- `_match_stats.html`, `_match_videos.html`, `_match_card.html`

### Phase 5: Utilities (2 templates)
- `clip.html`, `settings.html`, `error.html`

## Open Questions

- Should we use a full `<uk-theme-switcher>` in the nav for theme customization, or keep it simple with just dark/light mode? **Decision: Start with dark mode toggle only, add full theme switcher later if requested.**
- The `_upload_popup.html` currently uses `sessionStorage` to persist upload state across page loads. With `UIkit.notification()`, we lose persistence. **Decision: Keep a minimal hidden DOM element for state persistence, but show the notification as the primary UI.**
- The clip seeker uses custom-styled range inputs. `uk-range` provides consistent styling. **Decision: Use `uk-range` — it's themable and matches the rest of the UI.**
