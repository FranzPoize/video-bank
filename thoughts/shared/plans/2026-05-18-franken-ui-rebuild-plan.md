---
date: 2026-05-18
topic: "Franken UI Rebuild Implementation Plan"
status: ready
---

# Franken UI Rebuild — Implementation Plan

**Goal:** Replace all 382 lines of `style.css` and all inline styles in 18 Jinja2 templates with Franken UI CDN classes. Zero backend changes, no build pipeline.

**Architecture:** CDN-only integration — `franken-ui.css` from jsDelivr provides all component styles + Tailwind utility classes + theme system. UIkit JS provides interactive behaviors (dropdowns, notifications, dark mode). A `custom.css` (~40 lines) handles gaps Franken UI doesn't cover (warning badge, seeker label colors). All 18 templates get class-only updates — same Jinja2 variables, same HTMX attributes, same JS files.

**Design:** `thoughts/shared/designs/2026-05-18-franken-ui-rebuild-design.md`

---

## CDN Configuration (pinned to v2.1.2)

These are injected into `base.html` during Phase 1:

```html
<!-- Franken UI CSS (components + Tailwind utilities + theming) -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/[email protected]/dist/css/franken-ui.css">

<!-- UIkit JS (interactive components: dropdowns, notifications) -->
<script src="https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit-icons.min.js" defer></script>

<!-- Custom overrides (~40 lines) -->
<link rel="stylesheet" href="/static/css/custom.css">
```

**Why this works without a build pipeline:** The `franken-ui.css` in the CDN bundle is a pre-built CSS file that includes:
- All Franken UI component classes (`uk-btn`, `uk-card`, `uk-input`, etc.)
- Core Tailwind utility classes (`flex`, `grid`, `gap-*`, `text-*`, `bg-*`, `p-*`, `m-*`, etc.)
- CSS variable theme system (--primary, --background, etc.)
- Dark mode support via `.dark` class

**Critical note for implementers:** We use `uk-*` Franken UI component classes AND Tailwind utility classes like `flex`, `text-muted-foreground`, `bg-background`, etc. Both are included in the pre-built `franken-ui.css` from the CDN. No separate Tailwind CSS install needed.

---

## Dependency Graph

```
Batch 1 - Foundation (3 implementers parallel):  Task 1.1 (base.html), 1.2 (custom.css), 1.3 (_space_fragment.html)
Batch 2 - Upload System (2 implementers parallel): Task 2.1 (upload.html), 2.2 (_upload_popup.html + upload.js)
Batch 3 - Video Pages (4 implementers parallel):  Task 3.1 (index.html), 3.2 (_content.html), 3.3 (_video_grid.html), 3.4 (video_detail.html)
Batch 4 - Match System (5 implementers parallel):  Task 4.1 (match_list.html), 4.2 (match_detail.html), 4.3 (_match_stats.html), 4.4 (_match_videos.html), 4.5 (_match_card.html)
Batch 5 - Forms (2 implementers parallel):        Task 5.1 (edit.html), 5.2 (match_form.html)
Batch 6 - Utilities + Cleanup (4 implementers parallel): Task 6.1 (clip.html), 6.2 (settings.html), 6.3 (error.html), 6.4 (delete style.css)
```

---

## Batch 1: Foundation (3 implementers — parallel)

All tasks in Batch 1 have NO dependencies and run simultaneously.

### Task 1.1: `base.html` — Root layout, theme system, nav, dropdown, JS includes
**File:** `app/templates/base.html`
**Test:** Manual visual verification (see checklist at bottom)
**Depends:** none

**Changes required (35 lines → ~80 lines):**

Replace the entire file content:

```html
<!DOCTYPE html>
<html lang="{{ current_lang }}" class="uk-theme-neutral uk-radii-md uk-shadows-sm uk-font-sm">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ _("nav.video_bank") }}{% endblock %}</title>

    <!-- Theme initialization (before any CSS loads to prevent FOUC) -->
    <script>
        (function() {
            var html = document.documentElement;
            try {
                var stored = JSON.parse(localStorage.getItem("__FRANKEN__") || "{}");
                if (stored.mode === "dark" || (!stored.mode && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
                    html.classList.add("dark");
                }
                html.classList.add(stored.theme || "uk-theme-neutral");
                html.classList.add(stored.radii || "uk-radii-md");
                html.classList.add(stored.shadows || "uk-shadows-sm");
                html.classList.add(stored.font || "uk-font-sm");
            } catch(e) {}
        })();
    </script>

    <!-- Franken UI CDN -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/[email protected]/dist/css/franken-ui.css">
    <link rel="stylesheet" href="/static/css/custom.css">

    <!-- HTMX -->
    <script src="/static/js/htmx.min.js"></script>

    {% block extra_head %}{% endblock %}
</head>
<body class="bg-background text-foreground">
    <nav class="border-b bg-background flex items-center gap-4 px-6 py-3">
        <a href="/" class="text-foreground/80 hover:text-foreground font-semibold no-underline">{{ _("nav.video_bank") }}</a>
        <a href="/videos" class="text-foreground/80 hover:text-foreground font-semibold no-underline">{{ _("nav.videos") }}</a>
        <a href="/upload" class="text-foreground/80 hover:text-foreground font-semibold no-underline">{{ _("nav.upload") }}</a>
        <a href="/settings" class="text-foreground/80 hover:text-foreground font-semibold no-underline">{{ _("nav.settings") }}</a>

        <span id="space-indicator" class="ml-auto" hx-get="/api/space" hx-trigger="load"></span>

        <!-- Language dropdown (Franken UI dropdown with mode: click) -->
        <div class="uk-inline ml-2">
            <button class="uk-btn uk-btn-ghost uk-btn-sm" type="button">
                {{ current_flag }} {{ current_lang.upper() }}
                <span class="ml-1 text-xs opacity-70">▼</span>
            </button>
            <div class="uk-dropdown uk-dropdown min-w-36" data-uk-dropdown="mode: click">
                <ul class="uk-nav uk-nav-dropdown">
                    <li><a hx-post="/api/lang" hx-vals='{"lang": "en"}' hx-target="body">🇬🇧 {{ _("lang.en") }}</a></li>
                    <li><a hx-post="/api/lang" hx-vals='{"lang": "fr"}' hx-target="body">🇫🇷 {{ _("lang.fr") }}</a></li>
                </ul>
            </div>
        </div>
    </nav>

    <main class="uk-container py-8">
        {% block content %}{% endblock %}
    </main>

    {% include "_upload_popup.html" %}

    <!-- i18n translations for JavaScript -->
    <script>
        window.TRANSLATIONS = {
            "upload.untitled": "{{ _('upload.untitled') }}",
            "upload.completed": "{{ _('upload.completed') }}",
            "upload.failed": "{{ _('upload.failed') }}",
            "upload.network_error": "{{ _('upload.network_error') }}",
            "upload.resumed": "{{ _('upload.resumed') }}",
            "btn.retry": "{{ _('btn.retry') }}",
            "clip.creating": "{{ _('clip.creating') }}",
            "btn.create_clip": "{{ _('btn.create_clip') }}",
            "clip.min_duration": "{{ _('clip.min_duration') }}",
            "clip.failed": "{{ _('clip.failed') }}",
            "clip.network_error": "{{ _('clip.network_error') }}"
        };
        window._ = function(key) {
            return window.TRANSLATIONS[key] || key;
        };
    </script>

    <!-- Franken UI JS (defer ensures DOM is ready) -->
    <script src="https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit-icons.min.js"></script>

    <script src="/static/js/upload.js"></script>
    <script src="/static/js/clipper.js"></script>
</body>
</html>
```

**Key changes from current:**
1. `<html>` gets theme classes (`uk-theme-neutral uk-radii-md uk-shadows-sm uk-font-sm`)
2. Theme init script in `<head>` (before CSS) prevents FOUC
3. Removed `<link rel="stylesheet" href="/static/css/style.css">` — replaced by CDN + custom.css
4. `<body>` gets `bg-background text-foreground`
5. `<nav>` uses `border-b bg-background flex items-center gap-4 px-6 py-3`
6. Nav links use `text-foreground/80 hover:text-foreground font-semibold no-underline`
7. Language dropdown uses Franken UI `data-uk-dropdown="mode: click"` — removes the entire custom JS toggle block (lines 62-79 in current file)
8. Container changed from `<div class="container">` to `<main class="uk-container py-8">`
9. Franken UI JS loaded at end of `<body>` (before upload.js/clipper.js)
10. Space indicator uses `ml-auto` instead of inline `style="margin-left: auto"`

**Verify:** Load any page — nav should render with proper spacing, theme classes on `<html>`, dropdown opens on click, no FOUC. Language switch HTMX still works.

**Commit:** `feat(ui): migrate base.html to Franken UI with theme system and CDN`

---

### Task 1.2: `custom.css` — Create custom overrides file
**File:** `app/static/css/custom.css`
**Test:** Manual visual check on space indicator + clip page
**Depends:** none

Replace existing `custom.css` (31 lines) with comprehensive version (~50 lines):

```css
/* ── Warning badge (Franken UI doesn't ship one) ───── */
.uk-badge-warning {
  background: hsl(38 92% 50%);
  color: hsl(48 96% 89%);
}
.dark .uk-badge-warning {
  background: hsl(48 96% 89%);
  color: hsl(38 92% 50%);
}

/* ── Seeker label colors (clipper.js references these) ─ */
.seeker-label-start { color: hsl(var(--primary)); }
.seeker-label-end { color: hsl(var(--destructive)); }

/* ── Match card hover transitions ──────────────────── */
.hover-shadow-md:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.transition-shadow { transition: box-shadow 0.2s; }

/* ── Video player container (black background) ─────── */
.video-player { background: #000; border-radius: 0.5rem; overflow: hidden; margin-bottom: 1.5rem; }
.video-player video { width: 100%; display: block; max-height: 80vh; }
@media (max-width: 768px) {
  .video-player video { max-height: 50vh; }
}

/* ── Video wrapper full-width at large screens ──────── */
@media (min-width: 1200px) {
  .video-wrapper-full {
    width: min(90vw, 1400px);
    max-width: none;
    margin: 0;
    position: relative;
    left: 50%;
    transform: translateX(-50%);
  }
}

/* ── Empty state text alignment ────────────────────── */
.empty-state { text-align: center; padding: 3rem; color: hsl(var(--muted-foreground)); }

/* ── Page header (flex row that wraps on mobile) ───── */
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; }
.page-header .actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
@media (max-width: 768px) {
  .page-header { flex-direction: column; }
}
```

**Key design decisions:**
- `.seeker-label-start/end` used by `clipper.js` JS — must keep these class names
- `.video-player` used in `video_detail.html` and `clip.html` — keep for player wrapper
- `.page-header` used in `match_detail.html`, `match_list.html`, `video_detail.html` — keep for responsive header
- `.empty-state` used in `_video_grid.html`, `match_list.html`, `settings.html` — keep for consistent empty states
- All colors now use CSS variables (`--primary`, `--destructive`, `--muted-foreground`) from Franken UI theme system instead of hardcoded hex values
- `.hover-shadow-md` and `.transition-shadow` used on match cards

**Verify:** All pages load with proper styling. Space indicator warning badge shows yellow. Clip seeker labels are colored correctly. Video player has black background.

**Commit:** `feat(ui): create custom.css with Franken UI overrides for badges, seeker, video player`

---

### Task 1.3: `_space_fragment.html` — Space indicator with badge classes
**File:** `app/templates/_space_fragment.html`
**Test:** Manual visual — navigate between pages, indicator shows correct badge color
**Depends:** none (but should verify custom.css has `.uk-badge-warning`)

Replace entire file content:

```html
{% if space.error %}
<span class="uk-badge uk-badge-destructive">{{ _("space.unknown") }}</span>
{% elif space.percent_used <= 0.80 %}
<span class="uk-badge">{{ space.free_gb }} {{ _("space.gb_free") }}</span>
{% elif space.percent_used <= 0.90 %}
<span class="uk-badge uk-badge-warning">{{ space.free_gb }} {{ _("space.gb_free") }}</span>
{% else %}
<span class="uk-badge uk-badge-destructive">{{ space.free_gb }} {{ _("space.gb_free") }}</span>
{% endif %}
```

**Mapping:**

| State | Old class | New class |
|-------|-----------|-----------|
| Error | `space-critical` | `uk-badge uk-badge-destructive` |
| ≤80% | `space-ok` | `uk-badge` (default — success green) |
| ≤90% | `space-warn` | `uk-badge uk-badge-warning` (custom CSS) |
| >90% | `space-critical` | `uk-badge uk-badge-destructive` |

**Verify:** Space indicator in nav shows green (ok), yellow (warning), or red (critical/destructive) badge. Dark mode swaps badge colors correctly.

**Commit:** `feat(ui): migrate space fragment to uk-badge classes`

---

## Batch 2: Upload System (2 implementers — parallel)

Both tasks depend on Batch 1 (base.html provides CDN + notification JS).

### Task 2.1: `upload.html` — Upload form with Franken UI form controls
**File:** `app/templates/upload.html`
**Test:** Manual — form renders with stacked labels, styled inputs, custom file picker, error alerts
**Depends:** 1.1 (base.html has CDN + form styles)

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.upload") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<h1 class="uk-h2 mb-6">{{ _("page.upload") }}</h1>

{% if error %}
<div class="uk-alert uk-alert-destructive" data-uk-alert>
    <a class="uk-alert-close uk-close" data-uk-close></a>
    <p>{{ error }}</p>
</div>
{% endif %}

<form id="upload-form" action="/api/videos" method="post" enctype="multipart/form-data" class="uk-form-stacked space-y-4 max-w-lg">
    <div>
        <label class="uk-form-label" for="name">{{ _("form.video_name") }}</label>
        <input class="uk-input" type="text" id="name" name="name" required placeholder="{{ _('form.placeholder.name') }}">
    </div>

    <div>
        <label class="uk-form-label" for="file">{{ _("form.video_file") }}</label>
        <div data-uk-form-custom>
            <input type="file" id="file" name="file" accept="video/mp4,video/webm,video/quicktime" required>
            <button class="uk-btn uk-btn-default" type="button" tabindex="-1">{{ _("form.select_file") }}</button>
        </div>
    </div>

    <div>
        <label class="uk-form-label" for="tags">{{ _("form.tags") }}</label>
        <input class="uk-input" type="text" id="tags" name="tags" placeholder="{{ _('form.placeholder.tags') }}">
    </div>

    <button type="submit" class="uk-btn uk-btn-primary">{{ _("btn.upload") }}</button>
</form>

<p class="mt-4">
    <a href="/" class="text-primary hover:underline">{{ _("link.back_to_list") }}</a>
</p>
{% endblock %}
```

**Key changes:**
- `<h1>` uses `uk-h2 mb-6` instead of inline `style="margin-bottom:1.5rem"`
- Error div replaced with `uk-alert uk-alert-destructive` with close button
- Form uses `uk-form-stacked space-y-4 max-w-lg`
- Labels use `uk-form-label`
- Inputs use `uk-input`
- File input uses `data-uk-form-custom` wrapper with button
- Submit button uses `uk-btn uk-btn-primary`
- Back link uses `text-primary hover:underline`

**Verify:** Upload form renders correctly. File picker shows Franken UI button. Form submits via AJAX (upload.js). Errors show as destructive alerts. Empty state shows on /.

**Commit:** `feat(ui): migrate upload form to uk-form-stacked with uk-input and custom file picker`

---

### Task 2.2: `_upload_popup.html` + `upload.js` — Replace popup with notification API
**File:** `app/templates/_upload_popup.html` + `app/static/js/upload.js`
**Test:** Upload a video → notification appears at bottom-left, shows progress, success/error
**Depends:** 1.1 (base.html has CDN + UIkit JS)

**`_upload_popup.html`** — Reduce to minimal hidden state div:

```html
<div id="upload-popup" hidden></div>
```

**`upload.js`** — Update to use `UIkit.notification()` while keeping state persistence:

The JS changes are more surgical. Here are the exact modifications:

1. **Remove** the inline styles from `createPopup()` / `getPopup()` (lines 28-32) — popup is now just a hidden div
2. **In `showPopup()`** — Instead of showing the DOM popup, use `UIkit.notification()`:
3. **In `setPopupContent()`** — Keep for state persistence div, but also show notification
4. **Progress updates** — Show notification with progress
5. **Success** — Show notification with primary status
6. **Error** — Show notification with destructive status

Replace the entire `upload.js` file:

```javascript
/**
 * upload.js — Async upload with Franken UI notifications.
 *
 * Intercepts the upload form, creates an XHR with progress events,
 * and uses UIkit.notification() for user feedback while maintaining
 * a hidden state div for sessionStorage persistence across HTMX navigations.
 */
(function () {
  "use strict";

  function _(key) {
    return (window.TRANSLATIONS && window.TRANSLATIONS[key]) || key;
  }

  var UPLOAD_FORM_SELECTOR = "#upload-form";
  var STATE_DIV_ID = "upload-popup";
  var STORAGE_KEY = "upload-active";
  var activeNotification = null;

  // ── State persistence (hidden div + sessionStorage) ──

  function getStateDiv() {
    var el = document.getElementById(STATE_DIV_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = STATE_DIV_ID;
      el.hidden = true;
      document.body.appendChild(el);
    }
    return el;
  }

  function saveState(filename, status) {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ filename: filename, status: status })
      );
    } catch (_) {}
  }

  function clearState() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (_) {}
  }

  function restoreState() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      var state = JSON.parse(raw);
      if (state && state.filename) {
        var msg = state.filename + " — " +
          (state.status === "completed"
            ? _("upload.completed")
            : state.status === "failed"
              ? _("upload.failed")
              : _("upload.resumed"));
        UIkit.notification({
          message: msg,
          status: state.status === "completed" ? "primary" : "destructive",
          pos: "bottom-left",
          timeout: state.status === "completed" ? 5000 : 0
        });
      }
    } catch (_) {}
  }

  // ── Progress notification ──

  function showNotification(message, status, timeout) {
    if (activeNotification) {
      activeNotification.close();
    }
    activeNotification = UIkit.notification({
      message: message,
      status: status || "primary",
      pos: "bottom-left",
      timeout: timeout || 5000
    });
  }

  // ── Escaping ──

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Main upload handler ──

  function handleUpload(event) {
    var form = event.target;
    var formData = new FormData(form);
    var filename =
      formData.get("file") && formData.get("file").name
        ? formData.get("file").name
        : _("upload.untitled");

    event.preventDefault();

    var xhr = new XMLHttpRequest();

    // ── Progress ──
    xhr.upload.addEventListener("progress", function (e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        showNotification(
          escapeHtml(filename) + " " + pct + "%",
          "primary",
          0
        );
        saveState(filename, "uploading");
      }
    });

    // ── Load / complete ──
    xhr.addEventListener("load", function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        showNotification(
          "✓ " + escapeHtml(filename) + " — " + _("upload.completed"),
          "primary",
          5000
        );
        saveState(filename, "completed");
        activeNotification = null;

        setTimeout(function () {
          clearState();
          window.location.href = "/";
        }, 1500);
      } else {
        showNotification(
          "✗ " + escapeHtml(filename) + " — " + _("upload.failed"),
          "destructive",
          0
        );
        saveState(filename, "failed");
      }
    });

    // ── Error / network failure ──
    xhr.addEventListener("error", function () {
      showNotification(
        "✗ " + escapeHtml(filename) + " — " + _("upload.network_error"),
        "destructive",
        0
      );
      saveState(filename, "failed");
    });

    // ── Send ──
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.send(formData);
  }

  // ── Init ──

  function init() {
    restoreState();

    var form = document.querySelector(UPLOAD_FORM_SELECTOR);
    if (form) {
      form.addEventListener("submit", handleUpload);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

**Key changes from current `upload.js`:**
- Removed inline styles for popup creation (no longer needed)
- `showPopup()`/`setPopupContent()`/`hidePopup()` replaced with `showNotification()`
- Uses `UIkit.notification()` with `pos: 'bottom-left'` matching the original popup position
- Keeps `sessionStorage` state persistence and hidden state div for HTMX reload scenarios
- Progress: notification with `timeout: 0` (persistent) during upload
- Success: notification with `timeout: 5000` (auto-dismiss)
- Error: notification with `timeout: 0` (stays until dismissed)

**Verify:**
1. Upload a file → notification shows at bottom-left with progress percentage
2. Upload completes → notification shows "Completed" in green, auto-dismisses after 1.5s, redirects to /
3. Upload fails → notification shows error in red, stays until clicked
4. Network error → notification shows network error in red
5. Navigate away mid-upload and back → state restored from sessionStorage

**Commit:** `feat(ui): replace upload popup with UIkit.notification() API`

---

## Batch 3: Video Pages (4 implementers — parallel)

All tasks depend on Batch 1 (base.html has CDN + styles).

### Task 3.1: `index.html` — Video list page
**File:** `app/templates/index.html`
**Test:** Manual — page title styled, error shows as destructive alert
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.videos") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<h1 class="uk-h2 mb-6">{{ _("page.videos") }}</h1>

{% if error %}
<div class="uk-alert uk-alert-destructive" data-uk-alert>
    <a class="uk-alert-close uk-close" data-uk-close></a>
    <p>{{ error }}</p>
</div>
{% endif %}

{% include "_content.html" %}
{% endblock %}
```

**Changes:**
- `<h1>` uses `uk-h2 mb-6` instead of inline `style="margin-bottom: 1.5rem"`
- Error div uses `uk-alert uk-alert-destructive` with close button

**Verify:** Page loads with heading. Error messages (if any) show as destructive alerts. HTMX content swap still works.

**Commit:** `feat(ui): migrate index.html heading and error to uk classes`

---

### Task 3.2: `_content.html` — Filter bar
**File:** `app/templates/_content.html`
**Test:** Manual — filter bar renders inline, wraps on mobile, buttons toggle active state
**Depends:** 1.1

Replace entire file content:

```html
<div id="main-content">
    {% if all_tags and all_tags|length > 0 %}
    <div id="filter-bar" class="flex flex-wrap items-center gap-2 mb-6">
        <span class="text-sm text-muted-foreground font-semibold">{{ _("filter.label") }}</span>

        <a href="/videos"
           class="uk-btn uk-btn-sm {% if active_tag_id is none %}uk-btn-primary{% else %}uk-btn-ghost{% endif %}"
           hx-get="/videos"
           hx-target="#main-content"
           hx-swap="outerHTML"
           hx-push-url="true">
            {{ _("filter.all") }}
        </a>

        {% for tag in all_tags %}
        <a href="/videos?tag_id={{ tag.id }}"
           class="uk-btn uk-btn-sm {% if active_tag_id == tag.id %}uk-btn-primary{% else %}uk-btn-ghost{% endif %}"
           hx-get="/videos?tag_id={{ tag.id }}"
           hx-target="#main-content"
           hx-swap="outerHTML"
           hx-push-url="true">
            {{ tag.name }}
        </a>
        {% endfor %}
    </div>
    {% endif %}

    <div id="video-grid">
        {% include "_video_grid.html" %}
    </div>
</div>
```

**Changes:**
- Filter bar container: `flex flex-wrap items-center gap-2 mb-6` (replaces inline `display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:1.5rem; align-items:center`)
- Filter label: `text-sm text-muted-foreground font-semibold` (replaces inline font/color)
- Buttons: `uk-btn uk-btn-sm` with `uk-btn-primary` (active) or `uk-btn-ghost` (inactive) — replaces `btn btn-sm btn-primary / btn-inactive`

**Verify:** Filter bar renders correctly. Active button uses primary style, inactive uses ghost. HTMX clicks swap `#main-content` correctly.

**Commit:** `feat(ui): migrate filter bar to uk-btn classes with flex layout`

---

### Task 3.3: `_video_grid.html` — Video card grid
**File:** `app/templates/_video_grid.html`
**Test:** Manual — responsive grid, cards with thumbnails, tags as badges, empty states
**Depends:** 1.1

Replace entire file content:

```html
{% if videos %}
<div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
    {% for video in videos %}
    <div class="uk-card uk-card-body p-0 overflow-hidden">
        <div class="aspect-video bg-muted flex items-center justify-center text-muted-foreground text-3xl">
            {% if video.has_thumbnail and video.thumbnail_url %}
            <img src="{{ video.thumbnail_url }}" alt="{{ video.name }}" class="w-full h-full object-cover" fetchpriority="high">
            {% else %}
            &#9654;
            {% endif %}
        </div>
        <div class="p-3">
            <h3 class="uk-card-title text-sm mb-1">
                <a href="/videos/{{ video.id }}" class="text-foreground no-underline hover:text-primary">{{ video.name }}</a>
            </h3>
            <p class="text-xs text-muted-foreground mb-2">
                {{ _("video.uploaded") }} {{ video.upload_date }}
            </p>
            {% if video.tags and video.tags|length > 0 %}
            <div class="flex flex-wrap gap-1">
                {% for tag in video.tags %}
                <span class="uk-badge uk-badge-primary">{{ tag }}</span>
                {% endfor %}
            </div>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</div>
{% elif active_tag_id is not none %}
<div class="empty-state">
    <p>{{ _("video.no_videos_filter") }}</p>
    <p class="mt-4"><a href="/" class="uk-btn uk-btn-primary">{{ _("filter.clear") }}</a></p>
</div>
{% else %}
<div class="empty-state">
    <p>{{ _("video.no_videos_yet") }}</p>
    <p class="mt-4"><a href="/upload" class="uk-btn uk-btn-primary">{{ _("video.upload_first") }}</a></p>
</div>
{% endif %}
```

**Changes:**
- Grid: `grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4` (replaces inline `display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:1.5rem`)
- Card: `uk-card uk-card-body p-0 overflow-hidden` (replaces inline background/radius/shadow)
- Thumbnail area: `aspect-video bg-muted flex items-center justify-center text-muted-foreground text-3xl` (replaces inline styles)
- Card body: `p-3` (replaces `style="padding:0.75rem"`)
- Title: `uk-card-title text-sm mb-1` with link styling (replaces inline)
- Date: `text-xs text-muted-foreground mb-2` (replaces inline)
- Tag badge: `uk-badge uk-badge-primary` (replaces inline styled span)
- Empty state buttons: `uk-btn uk-btn-primary mt-4` (replaces `btn btn-primary`)

**Verify:** Responsive grid shows 1 col on mobile, 2 on tablet, 3-4 on desktop. Cards have consistent styling. Tags show as primary badges. Empty states centered with muted text.

**Commit:** `feat(ui): migrate video grid to uk-card with responsive grid layout`

---

### Task 3.4: `video_detail.html` — Single video view
**File:** `app/templates/video_detail.html`
**Test:** Manual — video player, tags, match context links, action buttons
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ video.name }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="mx-auto max-w-6xl">
    <div class="page-header">
        <div>
            <a href="/videos" class="text-primary no-underline hover:underline inline-block mb-2">{{ _("link.back_to_videos") }}</a>
            <h1 class="uk-h3 mb-1">{{ video.name }}</h1>
            <p class="text-muted-foreground text-sm">
                {{ _("video.uploaded") }} {{ video.upload_date }} &middot; {{ "%.1f"|format(video.file_size / (1024*1024)) }} {{ _("video.mb") }}
            </p>
        </div>
        <div class="actions">
            <a href="/videos/{{ video.id }}/clip" class="uk-btn uk-btn-primary uk-btn-sm">{{ _("btn.clip") }}</a>
            <a href="/videos/{{ video.id }}/edit" class="uk-btn uk-btn-primary uk-btn-sm">{{ _("btn.edit") }}</a>
        </div>
    </div>

    {% if video_matches and video_matches|length > 0 %}
    <div class="bg-muted/50 rounded-lg p-3 mb-6">
        <h3 class="text-sm text-muted-foreground mb-2">{{ _("match.linked_matches") }}</h3>
        {% for m in video_matches %}
        <a href="/matches/{{ m.id }}" class="inline-block mr-3 mb-1 px-3 py-1 bg-card rounded text-sm text-primary shadow-sm hover:bg-accent no-underline">
            {{ m.name }} ({{ m.match_date }})
        </a>
        {% endfor %}
    </div>
    {% endif %}

    <div class="video-player">
        <video controls preload="metadata">
            <source src="{{ video.video_url }}" type="{{ video.mime_type }}">
            {{ _("video.browser_no_video") }}
        </video>
    </div>

    {% if video.tags and video.tags|length > 0 %}
    <div class="mb-6">
        <h3 class="text-sm text-muted-foreground mb-2">{{ _("video.tags_heading") }}</h3>
        <div class="flex flex-wrap gap-2">
            {% for tag in video.tags %}
            <span class="uk-badge uk-badge-primary">{{ tag }}</span>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
```

**Changes:**
- Wrapper: `mx-auto max-w-6xl` (replaces `video-wrapper` class with inline max-width)
- Page header uses `.page-header` class from custom.css
- Back link: `text-primary no-underline hover:underline inline-block mb-2`
- Title: `uk-h3 mb-1`
- Meta: `text-muted-foreground text-sm`
- Action buttons: `uk-btn uk-btn-primary uk-btn-sm`
- Match context: `bg-muted/50 rounded-lg p-3 mb-6` with inline links styled
- Video player: keeps `.video-player` class (defined in custom.css)
- Tags heading: `text-sm text-muted-foreground mb-2`
- Tags: `uk-badge uk-badge-primary`

**Verify:** Video player renders in black container. Match context links shown conditionally. Tags display as primary badges. Back link and action buttons navigate correctly. Page responsive.

**Commit:** `feat(ui): migrate video detail page to uk classes with page-header layout`

---

## Batch 4: Match System (5 implementers — parallel)

All tasks depend on Batch 1 (base.html has CDN + styles).

### Task 4.1: `match_list.html` — Match list page
**File:** `app/templates/match_list.html`
**Test:** Manual — match cards in responsive grid, hover effects, empty state
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.matches") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="page-header">
    <h1 class="uk-h2">{{ _("page.matches") }}</h1>
    <div class="actions">
        <a href="/matches/new" class="uk-btn uk-btn-primary">{{ _("match.new") }}</a>
    </div>
</div>

{% if matches and matches|length > 0 %}
<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-4">
    {% for match in matches %}
    {% include "_match_card.html" %}
    {% endfor %}
</div>
{% else %}
<div class="empty-state">
    <p>{{ _("match.no_matches") }}</p>
    <p class="mt-4"><a href="/matches/new" class="uk-btn uk-btn-primary">{{ _("match.create_first") }}</a></p>
</div>
{% endif %}
{% endblock %}
```

**Changes:**
- Page header uses `.page-header` class from custom.css
- Heading: `uk-h2` (replaces plain `<h1>`)
- New match button: `uk-btn uk-btn-primary` (replaces `btn btn-primary`)
- Match grid: `grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-4` (replaces `.match-grid`)
- Empty state: uses `.empty-state` class from custom.css

**Note:** Match cards are rendered via `_match_card.html` (Task 4.5). The card template is swapped separately.

**Verify:** Match cards in responsive grid. New match button navigates to form. Empty state shows when no matches.

**Commit:** `feat(ui): migrate match list to uk-card grid with page-header layout`

---

### Task 4.2: `match_detail.html` — Match detail page
**File:** `app/templates/match_detail.html`
**Test:** Manual — match header with actions, notes block, stats, linked videos
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ match.name }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="page-header">
    <div>
        <a href="/" class="text-primary no-underline hover:underline inline-block mb-2">{{ _("match.back_to_list") }}</a>
        <h1 class="uk-h3 mb-1">{{ match.name }}</h1>
        <p class="text-muted-foreground text-sm">
            {{ match.match_date }}
            {% if match.opponent %} &middot; vs {{ match.opponent }}{% endif %}
            {% if match.location %} &middot; {{ match.location }}{% endif %}
        </p>
    </div>
    <div class="actions">
        <a href="/matches/{{ match.id }}/edit" class="uk-btn uk-btn-primary uk-btn-sm">{{ _("btn.edit") }}</a>
        <form action="/matches/{{ match.id }}/delete" method="post" style="display: inline;"
              onsubmit="return confirm('{{ _("match.confirm_delete") }}')">
            <button type="submit" class="uk-btn uk-btn-destructive uk-btn-sm">{{ _("btn.delete") }}</button>
        </form>
    </div>
</div>

{% if match.notes %}
<div class="bg-muted rounded-lg p-3 mb-6 text-foreground/80">
    {{ match.notes }}
</div>
{% endif %}

{% include "_match_stats.html" %}

<h2 class="uk-h4 mt-8 mb-3">{{ _("match.videos") }}</h2>
<div id="match-videos-section">
    {% include "_match_videos.html" %}
</div>
{% endblock %}
```

**Changes:**
- Page header uses `.page-header` class + actions div
- Back link: `text-primary no-underline hover:underline inline-block mb-2`
- Title: `uk-h3 mb-1`
- Meta: `text-muted-foreground text-sm`
- Action buttons: `uk-btn uk-btn-primary uk-btn-sm` / `uk-btn uk-btn-destructive uk-btn-sm`
- Notes: `bg-muted rounded-lg p-3 mb-6 text-foreground/80`
- Videos heading: `uk-h4 mt-8 mb-3`

**Verify:** Match header with edit/delete buttons. Notes render in muted background. Stats table and videos section included. Delete shows confirmation dialog.

**Commit:** `feat(ui): migrate match detail to uk classes with page-header layout`

---

### Task 4.3: `_match_stats.html` — Stats table with advanced stats
**File:** `app/templates/_match_stats.html`
**Test:** Manual — stat table with all columns, row hover, advanced stats row
**Depends:** 1.1

Replace entire file content:

```html
<div id="match-stats">
    <h3 class="uk-h4 mb-3">{{ _("match.box_score") }}</h3>
    <div class="uk-overflow-auto mb-2">
        <table class="uk-table uk-table-sm uk-table-divider text-xs min-w-[700px]">
            <thead>
                <tr>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.mp") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.pts") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.fga") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.fgm") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.fg_pct") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.two_pa") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.two_pm") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.two_pct") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.three_pa") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.three_pm") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.three_pct") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.fta") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.ftm") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.ft_pct") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.orb") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.drb") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.trb") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.ast") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.stl") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.blk") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.tov") }}</th>
                    <th class="bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]">{{ _("stat.pf") }}</th>
                </tr>
            </thead>
            <tbody class="[&_tr:hover]:bg-accent/50">
                <tr>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.minutes_played if match.minutes_played is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border font-bold text-destructive">{{ match.points if match.points is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ computed.fg_attempts }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ computed.fg_made }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{% if computed.fg_pct is not none %}{{ "%.1f"|format(computed.fg_pct) }}%{% else %}—{% endif %}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.two_point_attempts if match.two_point_attempts is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.two_point_made if match.two_point_made is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{% if computed.two_pct is not none %}{{ "%.1f"|format(computed.two_pct) }}%{% else %}—{% endif %}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.three_point_attempts if match.three_point_attempts is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.three_point_made if match.three_point_made is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{% if computed.three_pct is not none %}{{ "%.1f"|format(computed.three_pct) }}%{% else %}—{% endif %}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.free_throw_attempts if match.free_throw_attempts is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.free_throw_made if match.free_throw_made is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{% if computed.ft_pct is not none %}{{ "%.1f"|format(computed.ft_pct) }}%{% else %}—{% endif %}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.offensive_rebounds if match.offensive_rebounds is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.defensive_rebounds if match.defensive_rebounds is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.total_rebounds if match.total_rebounds is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.assists if match.assists is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.steals if match.steals is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.blocks if match.blocks is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.turnovers if match.turnovers is not none else "—" }}</td>
                    <td class="text-center px-1.5 py-2 whitespace-nowrap border-b border-border">{{ match.personal_fouls if match.personal_fouls is not none else "—" }}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="mt-6">
        <h3 class="uk-h4 mb-2">{{ _("match.advanced_stats") }}</h3>
        <div class="flex gap-6 p-3 bg-accent/50 rounded-lg flex-wrap">
            <div class="flex items-center gap-2">
                <span class="font-semibold text-sm text-muted-foreground">{{ _("stat.efg") }}</span>
                <span class="text-base font-bold text-foreground">{% if computed.efg_pct is not none %}{{ "%.1f"|format(computed.efg_pct) }}%{% else %}—{% endif %}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="font-semibold text-sm text-muted-foreground">{{ _("stat.ts") }}</span>
                <span class="text-base font-bold text-foreground">{% if computed.ts_pct is not none %}{{ "%.1f"|format(computed.ts_pct) }}%{% else %}—{% endif %}</span>
            </div>
        </div>
    </div>
</div>
```

**Key changes:**
- Table wrapper: `uk-overflow-auto mb-2` (replaces `.stats-table-wrapper`)
- Table: `uk-table uk-table-sm uk-table-divider text-xs min-w-[700px]` (replaces `.stats-table`)
- Header cells: `bg-muted text-muted-foreground text-center font-semibold whitespace-nowrap px-1.5 py-2 text-[0.7rem]`
- Data cells: `text-center px-1.5 py-2 whitespace-nowrap border-b border-border`
- Points column: additional `font-bold text-destructive`
- Row hover: `[&_tr:hover]:bg-accent/50` on tbody
- Advanced stats row: `flex gap-6 p-3 bg-accent/50 rounded-lg flex-wrap`

**Note:** The header row uses individual cell classes instead of `<thead class="bg-muted">` because the data cells in the single-row body need separate styling too. The `text-[0.7rem]` is a Tailwind arbitrary value that's included in the pre-built CDN CSS.

**Verify:** Stats table renders all columns. Header uses muted background. Points highlighted in destructive color. Row hover works. Horizontal scroll on narrow screens. Advanced stats show below.

**Commit:** `feat(ui): migrate stats table to uk-table classes with muted header`

---

### Task 4.4: `_match_videos.html` — Linked videos and link form
**File:** `app/templates/_match_videos.html`
**Test:** Manual — linked videos with remove buttons, link video form, HTMX swaps
**Depends:** 1.1

Replace entire file content:

```html
{% if match.videos and match.videos|length > 0 %}
<div class="space-y-2">
    {% for video in match.videos %}
    <div class="flex items-center gap-3 p-3 bg-card rounded-lg shadow-sm">
        <a href="/videos/{{ video.id }}" class="font-semibold text-primary no-underline hover:underline">{{ video.name }}</a>
        {% if video.tags and video.tags|length > 0 %}
        <div class="flex gap-1 ml-auto">
            {% for tag in video.tags %}
            <span class="uk-badge uk-badge-primary">{{ tag }}</span>
            {% endfor %}
        </div>
        {% endif %}
        <div class="flex items-center gap-2 ml-auto">
            <button class="uk-btn uk-btn-destructive uk-btn-sm"
                    hx-post="/api/matches/{{ match.id }}/videos/{{ video.id }}/remove"
                    hx-target="#match-videos-section"
                    hx-swap="outerHTML">
                {{ _("match.remove_video") }}
            </button>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<p class="text-muted-foreground">{{ _("match.no_videos") }}</p>
{% endif %}

{% if unlinked_videos and unlinked_videos|length > 0 %}
<form class="flex items-center gap-2 mt-4 p-3 bg-accent/50 rounded-lg"
      hx-post="/api/matches/{{ match.id }}/videos"
      hx-target="#match-videos-section"
      hx-swap="outerHTML">
    <select name="video_id" class="uk-select uk-form-sm flex-1">
        {% for v in unlinked_videos %}
        <option value="{{ v.id }}">{{ v.name }}</option>
        {% endfor %}
    </select>
    <button type="submit" class="uk-btn uk-btn-primary uk-btn-sm">{{ _("match.link_video") }}</button>
</form>
{% endif %}
```

**Changes:**
- Linked videos: `space-y-2` (replaces `.linked-videos`)
- Video item: `flex items-center gap-3 p-3 bg-card rounded-lg shadow-sm` (replaces `.linked-video-item`)
- Video link: `font-semibold text-primary no-underline hover:underline` (replaces `.linked-video-link`)
- Tag badge: `uk-badge uk-badge-primary` (replaces `.tag-badge`)
- Remove button: `uk-btn uk-btn-destructive uk-btn-sm` (replaces `btn btn-danger btn-sm`)
- No videos: `text-muted-foreground` (replaces inline `color:#888`)
- Link video form: `flex items-center gap-2 mt-4 p-3 bg-accent/50 rounded-lg` (replaces `.link-video-form`)
- Select: `uk-select uk-form-sm flex-1` (replaces plain `<select>`)
- Link button: `uk-btn uk-btn-primary uk-btn-sm` (replaces `btn btn-primary btn-sm`)

**Verify:** Existing videos display as card items with primary tag badges. Remove button triggers HTMX removal. No videos message shown when empty. Link form shows unlinked videos in styled select dropdown. HTMX swap targets `#match-videos-section`.

**Commit:** `feat(ui): migrate linked videos section to uk-card and uk-select classes`

---

### Task 4.5: `_match_card.html` — Match card fragment for HTMX swaps
**File:** `app/templates/_match_card.html`
**Test:** Manual — card renders correctly when HTMX-swapped into match list
**Depends:** 1.1

Replace entire file content:

```html
<div class="uk-card uk-card-body hover-shadow-md transition-shadow">
    <a href="/matches/{{ match.id }}" class="block p-5 no-underline text-foreground">
        <h3 class="uk-card-title text-primary mb-2">{{ match.name }}</h3>
        <div class="flex flex-wrap gap-3 text-sm text-muted-foreground mb-3">
            <span>{{ match.match_date }}</span>
            {% if match.opponent %}
            <span>vs {{ match.opponent }}</span>
            {% endif %}
            {% if match.location %}
            <span>{{ match.location }}</span>
            {% endif %}
        </div>
        {% if match.points is not none %}
        <div class="flex gap-4 text-sm text-foreground/70 pt-3 border-t border-border">
            <span class="font-bold text-destructive">{{ match.points }} {{ _("stat.pts") }}</span>
            {% if match.assists is not none %}
            <span>{{ match.assists }} {{ _("stat.ast") }}</span>
            {% endif %}
            {% if match.total_rebounds is not none %}
            <span>{{ match.total_rebounds }} {{ _("stat.trb") }}</span>
            {% endif %}
        </div>
        {% endif %}
    </a>
</div>
```

**Changes:**
- Card wrapper: `uk-card uk-card-body hover-shadow-md transition-shadow` (replaces `.match-card` — custom CSS provides the hover transition)
- Card link: `block p-5 no-underline text-foreground` (replaces `.match-card-link`)
- Title: `uk-card-title text-primary mb-2` (replaces `.match-card-title`)
- Meta: `flex flex-wrap gap-3 text-sm text-muted-foreground mb-3` (replaces `.match-card-meta`)
- Stats row: `flex gap-4 text-sm text-foreground/70 pt-3 border-t border-border` (replaces `.match-card-stats`)
- Point highlight: `font-bold text-destructive` (replaces `.stat-highlight`)

**Verify:** Card renders with proper padding, title in primary color, meta in muted text. Stats row separated by border-top. Destructive-colored points highlight. Card hover shows shadow transition. Consistent with cards on `match_list.html`.

**Commit:** `feat(ui): migrate match card fragment to uk-card with hover transition`

---

## Batch 5: Forms (2 implementers — parallel)

### Task 5.1: `edit.html` — Edit video form
**File:** `app/templates/edit.html`
**Test:** Manual — form in card layout, danger zone section, delete button
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.edit_video") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="max-w-xl mx-auto">
    <a href="/videos/{{ video.id }}" class="text-primary no-underline hover:underline inline-block mb-4">{{ _("link.back_to_video") }}</a>

    <h1 class="uk-h3 mb-6">{{ _("page.edit_video") }}</h1>

    {% if error %}
    <div class="uk-alert uk-alert-destructive" data-uk-alert>
        <a class="uk-alert-close uk-close" data-uk-close></a>
        <p>{{ error }}</p>
    </div>
    {% endif %}

    <form action="/videos/{{ video.id }}/edit" method="post" class="uk-card uk-card-body space-y-4">
        <div>
            <label class="uk-form-label" for="name">{{ _("form.video_name") }}</label>
            <input class="uk-input" type="text" id="name" name="name" required value="{{ video.name }}">
        </div>

        <div>
            <label class="uk-form-label" for="tags">{{ _("form.tags") }}</label>
            <input class="uk-input" type="text" id="tags" name="tags" value="{{ tags_str }}">
        </div>

        <p class="text-xs text-muted-foreground mb-4">
            {{ _("edit.file_info") }} {{ video.original_name }} ({{ "%.1f"|format(video.file_size / (1024*1024)) }} {{ _("video.mb") }})
        </p>

        <div class="flex gap-2">
            <button type="submit" class="uk-btn uk-btn-primary">{{ _("btn.save_changes") }}</button>
            <a href="/videos/{{ video.id }}" class="uk-btn uk-btn-ghost">{{ _("btn.cancel") }}</a>
        </div>
    </form>

    <hr class="my-8 border-border">

    <div class="uk-card uk-card-body">
        <h2 class="text-destructive text-lg font-semibold mb-2">{{ _("edit.danger_zone") }}</h2>
        <p class="text-sm text-muted-foreground mb-4">
            {{ _("edit.danger_desc") }}
        </p>
        <form action="/videos/{{ video.id }}/delete" method="post" onsubmit="return confirm('{{ _("edit.confirm_delete") }} {{ video.name }}?');">
            <button type="submit" class="uk-btn uk-btn-destructive">{{ _("btn.delete_video") }}</button>
        </form>
    </div>
</div>
{% endblock %}
```

**Changes:**
- Wrapper: `max-w-xl mx-auto` (replaces inline `max-width:600px; margin:0 auto`)
- Back link: `text-primary no-underline hover:underline inline-block mb-4`
- Title: `uk-h3 mb-6`
- Error: `uk-alert uk-alert-destructive` with close button
- Form card: `uk-card uk-card-body space-y-4` (replaces inline styled div)
- Labels: `uk-form-label`
- Inputs: `uk-input`
- File info: `text-xs text-muted-foreground mb-4`
- Button row: `flex gap-2`
- Save: `uk-btn uk-btn-primary`
- Cancel: `uk-btn uk-btn-ghost`
- Divider: `hr class="my-8 border-border"` (replaces inline styled `<hr>`)
- Danger zone card: `uk-card uk-card-body`
- Danger heading: `text-destructive text-lg font-semibold mb-2`
- Danger description: `text-sm text-muted-foreground mb-4`
- Delete button: `uk-btn uk-btn-destructive`

**Verify:** Form renders inside card. Danger zone visually distinct with destructive heading. Delete button uses destructive style. Cancel link navigates back.

**Commit:** `feat(ui): migrate edit form to uk-card layout with uk-input classes`

---

### Task 5.2: `match_form.html` — Create/Edit match form
**File:** `app/templates/match_form.html`
**Test:** Manual — form grid, stats grid with compact inputs, textarea, save/cancel
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{% if match %}{{ _("match.edit") }}{% else %}{{ _("match.new") }}{% endif %} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<h1 class="uk-h2 mb-6">{% if match %}{{ _("match.edit") }}{% else %}{{ _("match.new") }}{% endif %}</h1>

{% if errors and errors|length > 0 %}
<div class="uk-alert uk-alert-destructive" data-uk-alert>
    <a class="uk-alert-close uk-close" data-uk-close></a>
    {% for err in errors %}
    <p>{{ err }}</p>
    {% endfor %}
</div>
{% endif %}

<form action="{% if match %}/api/matches/{{ match.id }}{% else %}/api/matches{% endif %}" method="post" class="uk-form-stacked">
    <div class="grid gap-4 sm:grid-cols-2">
        <div>
            <label class="uk-form-label">{{ _("match.form.name") }}</label>
            <input class="uk-input" type="text" name="name" value="{{ match.name if match else '' }}" required>
        </div>
        <div>
            <label class="uk-form-label">{{ _("match.form.date") }}</label>
            <input class="uk-input" type="date" name="match_date" value="{{ match.match_date if match else '' }}" required>
        </div>
        <div>
            <label class="uk-form-label">{{ _("match.form.opponent") }}</label>
            <input class="uk-input" type="text" name="opponent" value="{{ match.opponent if match else '' }}">
        </div>
        <div>
            <label class="uk-form-label">{{ _("match.form.location") }}</label>
            <input class="uk-input" type="text" name="location" value="{{ match.location if match else '' }}">
        </div>
    </div>

    <h3 class="uk-h4 mt-6 mb-3">{{ _("match.box_score") }}</h3>
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.mp") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="minutes_played" step="0.1" min="0"
                   value="{{ match.minutes_played if match and match.minutes_played is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.pts") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="points" min="0"
                   value="{{ match.points if match and match.points is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.two_pa") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="two_point_attempts" min="0"
                   value="{{ match.two_point_attempts if match and match.two_point_attempts is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.two_pm") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="two_point_made" min="0"
                   value="{{ match.two_point_made if match and match.two_point_made is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.three_pa") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="three_point_attempts" min="0"
                   value="{{ match.three_point_attempts if match and match.three_point_attempts is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.three_pm") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="three_point_made" min="0"
                   value="{{ match.three_point_made if match and match.three_point_made is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.fta") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="free_throw_attempts" min="0"
                   value="{{ match.free_throw_attempts if match and match.free_throw_attempts is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.ftm") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="free_throw_made" min="0"
                   value="{{ match.free_throw_made if match and match.free_throw_made is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.orb") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="offensive_rebounds" min="0"
                   value="{{ match.offensive_rebounds if match and match.offensive_rebounds is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.drb") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="defensive_rebounds" min="0"
                   value="{{ match.defensive_rebounds if match and match.defensive_rebounds is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.trb") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="total_rebounds" min="0"
                   value="{{ match.total_rebounds if match and match.total_rebounds is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.ast") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="assists" min="0"
                   value="{{ match.assists if match and match.assists is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.stl") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="steals" min="0"
                   value="{{ match.steals if match and match.steals is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.blk") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="blocks" min="0"
                   value="{{ match.blocks if match and match.blocks is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.tov") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="turnovers" min="0"
                   value="{{ match.turnovers if match and match.turnovers is not none else '' }}">
        </div>
        <div>
            <label class="text-xs text-muted-foreground mb-0.5 block">{{ _("stat.pf") }}</label>
            <input class="uk-input uk-form-sm" type="number" name="personal_fouls" min="0"
                   value="{{ match.personal_fouls if match and match.personal_fouls is not none else '' }}">
        </div>
    </div>

    <div class="mt-6">
        <label class="uk-form-label">{{ _("match.form.notes") }}</label>
        <textarea class="uk-textarea" name="notes" rows="3">{{ match.notes if match else '' }}</textarea>
    </div>

    <div class="mt-6 flex gap-3">
        <button type="submit" class="uk-btn uk-btn-primary">{{ _("match.form.save") }}</button>
        <a href="/{% if match %}matches/{{ match.id }}{% endif %}" class="uk-btn uk-btn-ghost">{{ _("match.form.cancel") }}</a>
    </div>
</form>
{% endblock %}
```

**Changes:**
- Title: `uk-h2 mb-6`
- Errors: `uk-alert uk-alert-destructive` with close button
- Form: `uk-form-stacked`
- 4-field grid (name/date/opponent/location): `grid gap-4 sm:grid-cols-2`
- Labels in grid: `uk-form-label`
- Inputs in grid: `uk-input`
- Box score heading: `uk-h4 mt-6 mb-3`
- Stats grid: `grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3` (replaces `.stats-form-grid`)
- Stat labels: `text-xs text-muted-foreground mb-0.5 block`
- Stat inputs: `uk-input uk-form-sm`
- Notes textarea: `uk-textarea`
- Button row: `mt-6 flex gap-3`
- Save: `uk-btn uk-btn-primary`
- Cancel: `uk-btn uk-btn-ghost`

**Verify:** 2-column grid for main info. Stats grid renders compact inputs in 2-4 responsive columns. Textarea has consistent styling. Save/cancel buttons work.

**Commit:** `feat(ui): migrate match form to uk-form-stacked with responsive stat grid`

---

## Batch 6: Utilities + Cleanup (4 implementers — parallel)

### Task 6.1: `clip.html` — Clip creation page with seeker controls
**File:** `app/templates/clip.html`
**Test:** Manual — video player, range sliders, time display, create button
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.create_clip") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="mx-auto max-w-6xl">
    <div class="mb-4">
        <a href="/videos/{{ video.id }}" class="text-primary no-underline hover:underline inline-block mb-2">
            {{ _("link.back_to_video") }}
        </a>
        <h1 class="uk-h3 mb-1">{{ _("page.create_clip") }}</h1>
        <p class="text-muted-foreground text-sm">
            {{ _("clip.source") }} {{ video.name }}
        </p>
    </div>

    <div id="clipper">
        <!-- Video Player -->
        <div class="video-player">
            <video id="clip-video" controls preload="metadata">
                <source src="{{ video.video_url }}" type="{{ video.mime_type }}">
                {{ _("video.browser_no_video") }}
            </video>
        </div>

        <!-- Seeker Controls -->
        <div id="seeker" class="bg-card rounded-lg shadow-sm p-4 mb-4">
            <div class="flex items-center gap-3 mb-3">
                <span class="seeker-label-start font-semibold text-sm min-w-[3rem]">{{ _("clip.start") }}</span>
                <input type="range" id="clip-start" min="0" max="100" step="0.1" value="0" class="uk-range flex-1">
            </div>
            <div class="flex items-center gap-3 mb-3">
                <span class="seeker-label-end font-semibold text-sm min-w-[3rem]">{{ _("clip.end") }}</span>
                <input type="range" id="clip-end" min="0" max="100" step="0.1" value="0" class="uk-range flex-1">
            </div>

            <!-- Timestamp Display -->
            <div id="clip-times" class="text-center text-base font-semibold text-foreground py-2">
                0s / 0s (0s)
            </div>

            <p class="text-center text-xs text-muted-foreground mb-3">
                {{ _("clip.hint") }}
            </p>

            <!-- Error Display -->
            <div id="clip-error" class="text-destructive text-sm mb-2 text-center"></div>

            <!-- Create Button -->
            <div class="text-center">
                <button id="create-clip-btn" class="uk-btn uk-btn-primary px-8 py-3 text-base"
                        data-video-id="{{ video.id }}">
                    {{ _("btn.create_clip") }}
                </button>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Changes:**
- Wrapper: `mx-auto max-w-6xl` (replaces `.video-wrapper`)
- Back link: `text-primary no-underline hover:underline inline-block mb-2`
- Title: `uk-h3 mb-1`
- Source text: `text-muted-foreground text-sm`
- Seeker controls: `bg-card rounded-lg shadow-sm p-4 mb-4` (replaces `.seeker-controls`)
- Seeker rows: `flex items-center gap-3 mb-3` (replaces `.seeker-row`)
- Start label: `seeker-label-start font-semibold text-sm min-w-[3rem]` (references CSS `.seeker-label-start` from custom.css)
- End label: `seeker-label-end font-semibold text-sm min-w-[3rem]` (references CSS `.seeker-label-end` from custom.css)
- Range inputs: `uk-range flex-1` (replaces `.seeker-slider`)
- Time display: `text-center text-base font-semibold text-foreground py-2` (replaces `.seeker-times`)
- Hint: `text-center text-xs text-muted-foreground mb-3` (replaces `.seeker-hint`)
- Error: `text-destructive text-sm mb-2 text-center` (replaces `.seeker-error`)
- Create button: `uk-btn uk-btn-primary px-8 py-3 text-base` (replaces `btn btn-primary` with inline padding)

**Note:** The `seeker-label-start` and `seeker-label-end` CSS classes are defined in `custom.css` (Task 1.2). These use `color: hsl(var(--primary))` and `color: hsl(var(--destructive))` respectively, which reference Franken UI theme CSS variables.

**Verify:** Video player renders in black container. Range sliders use `uk-range` styling. Start label is primary-colored, end is destructive-colored. Time display updates (via clipper.js). Create button triggers clip creation.

**Commit:** `feat(ui): migrate clip page seeker controls to uk-range and card classes`

---

### Task 6.2: `settings.html` — Tag management page
**File:** `app/templates/settings.html`
**Test:** Manual — tag table with rename toggle, delete confirmation, empty state
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.settings") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto">
    <h1 class="uk-h2 mb-6">{{ _("page.settings") }}</h1>

    {% if error_code == "empty" %}
    <div class="uk-alert uk-alert-destructive" data-uk-alert>
        <a class="uk-alert-close uk-close" data-uk-close></a>
        <p>{{ _("tag.error.empty") }}</p>
    </div>
    {% elif error_code == "duplicate" %}
    <div class="uk-alert uk-alert-destructive" data-uk-alert>
        <a class="uk-alert-close uk-close" data-uk-close></a>
        <p>{{ _("tag.error.duplicate") }}</p>
    </div>
    {% endif %}

    <div class="uk-card uk-card-body">
        <h2 class="uk-card-title mb-4">{{ _("tag_management") }}</h2>

        {% if tags %}
        <div class="border border-border rounded-lg overflow-hidden">
            <!-- Header -->
            <div class="flex px-4 py-3 bg-muted font-semibold text-sm">
                <div class="flex-[3]">{{ _("tag.name") }}</div>
                <div class="flex-1 text-center">{{ _("tag.videos") }}</div>
                <div class="flex-[2] text-right">{{ _("tag.actions") }}</div>
            </div>

            <!-- Tag rows -->
            {% for tag in tags %}
            <div id="tag-row-{{ tag.id }}" class="flex items-center px-4 py-3 border-t border-border">
                <!-- View mode -->
                <div id="tag-view-{{ tag.id }}" class="flex w-full items-center">
                    <div class="flex-[3] font-medium">{{ tag.name }}</div>
                    <div class="flex-1 text-center text-muted-foreground">{{ tag.video_count }}</div>
                    <div class="flex-[2] text-right flex gap-2 justify-end">
                        <button type="button" class="uk-btn uk-btn-ghost uk-btn-sm" onclick="toggleRename({{ tag.id }})">{{ _("tag.rename") }}</button>
                        <form action="/api/tags/{{ tag.id }}/delete" method="post" style="display: inline;" onsubmit="return confirm('{{ _("tag.confirm_delete") }}');">
                            <button type="submit" class="uk-btn uk-btn-destructive uk-btn-sm">{{ _("tag.delete") }}</button>
                        </form>
                    </div>
                </div>

                <!-- Edit mode (hidden initially) -->
                <div id="tag-edit-{{ tag.id }}" class="hidden w-full">
                    <form action="/api/tags/{{ tag.id }}/rename" method="post" class="flex w-full items-center gap-2">
                        <div class="flex-[3]">
                            <input type="text" name="new_name" id="rename-input-{{ tag.id }}" value="{{ tag.name }}"
                                   class="uk-input uk-form-sm w-full" required>
                        </div>
                        <div class="flex-1 text-center text-muted-foreground">{{ tag.video_count }}</div>
                        <div class="flex-[2] text-right flex gap-2 justify-end">
                            <button type="submit" class="uk-btn uk-btn-primary uk-btn-sm">{{ _("tag.save") }}</button>
                            <button type="button" class="uk-btn uk-btn-ghost uk-btn-sm" onclick="toggleRename({{ tag.id }})">{{ _("tag.cancel") }}</button>
                        </div>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="empty-state">
            <p>{{ _("tag.no_tags") }}</p>
        </div>
        {% endif %}
    </div>
</div>

<script>
function toggleRename(tagId) {
    var viewEl = document.getElementById('tag-view-' + tagId);
    var editEl = document.getElementById('tag-edit-' + tagId);
    var inputEl = document.getElementById('rename-input-' + tagId);

    if (viewEl.style.display === 'none') {
        viewEl.style.display = 'flex';
        editEl.style.display = 'none';
    } else {
        viewEl.style.display = 'none';
        editEl.style.display = 'flex';
        if (inputEl) {
            inputEl.focus();
            inputEl.select();
        }
    }
}
</script>
{% endblock %}
```

**Changes:**
- Wrapper: `max-w-2xl mx-auto` (replaces inline `max-width:800px; margin:0 auto`)
- Title: `uk-h2 mb-6`
- Error: `uk-alert uk-alert-destructive` with close button
- Tag management card: `uk-card uk-card-body` (replaces inline styled div)
- Card heading: `uk-card-title mb-4` (replaces inline styled `<h2>`)
- Table container: `border border-border rounded-lg overflow-hidden`
- Header row: `flex px-4 py-3 bg-muted font-semibold text-sm`
- Tag row: `flex items-center px-4 py-3 border-t border-border`
- Rename button: `uk-btn uk-btn-ghost uk-btn-sm`
- Delete button: `uk-btn uk-btn-destructive uk-btn-sm`
- Edit form input: `uk-input uk-form-sm w-full`
- Edit save button: `uk-btn uk-btn-primary uk-btn-sm`
- Edit cancel button: `uk-btn uk-btn-ghost uk-btn-sm`
- Empty state: uses `.empty-state` class from custom.css

**Note:** The `flex-[3]`, `flex-1`, `flex-[2]` classes are Tailwind flex utilities included in the CDN CSS. The `uk-form-sm` class reduces input height for the inline edit form.

**Verify:** Tag table renders as flex-based layout. Rename toggles view/edit modes. Delete shows confirmation dialog. Empty state when no tags exist.

**Commit:** `feat(ui): migrate settings tag management to uk-card and border classes`

---

### Task 6.3: `error.html` — Error page
**File:** `app/templates/error.html`
**Test:** Manual — error page centered, status code large, home link works
**Depends:** 1.1

Replace entire file content:

```html
{% extends "base.html" %}
{% block title %}{{ _("page.error") }} — {{ _("nav.video_bank") }}{% endblock %}

{% block content %}
<div class="uk-text-center py-16">
    <h1 class="text-5xl text-destructive mb-4">{{ status_code }}</h1>
    <p class="text-lg text-muted-foreground mb-8">{{ detail }}</p>
    <a href="/" class="uk-btn uk-btn-primary">{{ _("btn.go_home") }}</a>
</div>
{% endblock %}
```

**Changes:**
- Container: `uk-text-center py-16` (replaces inline `text-align:center; padding:3rem`)
- Status code: `text-5xl text-destructive mb-4` (replaces inline font-size/color — Franken UI's text-5xl is ~3rem)
- Detail: `text-lg text-muted-foreground mb-8` (replaces inline styles)
- Home button: `uk-btn uk-btn-primary`

**Note:** The design doc mentioned `uk-hero-lg` for the status code, but Franken UI/UIkit's `uk-hero-lg` class is part of UIkit's typography, which may not be in the Tailwind-based Franken UI CDN build. Using `text-5xl` (Tailwind utility from CDN) is more reliable and produces a similar visual result (~3rem).

**Verify:** Error page centered. Status code large and destructive-colored. Detail message in muted text. Home button navigates to /. Works for all HTTP error codes.

**Commit:** `feat(ui): migrate error page to uk-text-center with text-destructive status code`

---

### Task 6.4: Delete `style.css` and verify everything works
**File:** `app/static/css/style.css` — **DELETE**
**Test:** Run `pytest tests/ -v`, check no 404 for missing style.css, visual check of all pages
**Depends:** 1.1, 1.2, 1.3, all batch 3 tasks (video pages use style.css classes)

**Actions:**
1. Delete `app/static/css/style.css`
2. Verify that `base.html` no longer links to it (Task 1.1 removed the link)
3. Run `pytest tests/ -v` — all tests must pass (they test backend, not frontend)
4. Manual visual check of every page in light mode
5. Manual visual check of every page in dark mode (add `class="dark"` to `<html>`)
6. Manual visual check of every page at 375px viewport width

**Key verification that `style.css` classes are fully replaced:**
- `btn btn-primary btn-danger btn-inactive btn-sm` → `uk-btn uk-btn-primary uk-btn-destructive uk-btn-ghost uk-btn-sm`
- `error` → `uk-alert uk-alert-destructive`
- `empty-state` → kept in custom.css (used by multiple templates)
- `space-ok space-warn space-critical` → `uk-badge uk-badge-warning uk-badge-destructive`
- `match-grid match-card match-card-link match-card-title match-card-meta match-card-stats` → `uk-card` with Tailwind utilities
- `stats-table stats-table-wrapper stat-pts stat-highlight` → `uk-table uk-table-sm` with Tailwind utilities
- `advanced-stats-row advanced-stat advanced-stat-label advanced-stat-value` → Tailwind utility classes
- `linked-videos linked-video-item linked-video-link tag-badge` → Tailwind utility classes
- `link-video-form` → Tailwind utility classes
- `match-context match-context-item` → Tailwind utility classes
- `seeker-controls seeker-row seeker-label seeker-slider seeker-times seeker-hint seeker-error` → Tailwind utility classes + custom CSS for label colors
- `lang-dropdown lang-btn lang-arrow lang-menu lang-flag lang-code` → Franken UI dropdown component
- `stats-form-grid stat-field` → Tailwind grid utility classes
- `page-header .actions` → kept in custom.css (responsive flex layout)
- `video-player video-wrapper` → kept in custom.css (black background, responsive)

**Verify:** `pytest tests/ -v` passes. No 404 errors in browser console. All pages render correctly in light and dark mode.

**Commit:** `chore(ui): remove style.css — fully replaced by Franken UI CDN + custom.css`

---

## Verification Checklist (run after all batches complete)

### Backend
- [ ] `pytest tests/ -v` — all tests pass (backend unchanged)

### Foundation (Batch 1)
- [ ] All pages load with Franken UI CDN styles applied
- [ ] `<html>` has theme classes (`uk-theme-neutral uk-radii-md uk-shadows-sm uk-font-sm`)
- [ ] Dark mode works (add `class="dark"` to `<html>`, check all pages)
- [ ] Language dropdown opens on click with `data-uk-dropdown="mode: click"`
- [ ] HTMX language switch still works
- [ ] Space indicator shows correct badge color per storage level

### Video Pages (Batch 3)
- [ ] Video grid responsive (1 col mobile, 2 tablet, 3-4 desktop)
- [ ] Video cards use `uk-card` styling with proper aspect ratio for thumbnails
- [ ] Tags display as `uk-badge uk-badge-primary`
- [ ] Filter bar buttons toggle `uk-btn-primary`/`uk-btn-ghost`
- [ ] HTMX filter/sort still works
- [ ] Empty states render centered with muted text

### Upload (Batch 2)
- [ ] Upload form has stacked labels (`uk-form-stacked`), styled inputs (`uk-input`)
- [ ] File input uses Franken UI custom file picker (`data-uk-form-custom`)
- [ ] `UIkit.notification()` shows on upload start/progress/complete/error
- [ ] Upload state persisted in sessionStorage across HTMX navigations

### Match System (Batch 4)
- [ ] Match list cards in responsive grid with hover shadow
- [ ] Stats table renders all columns with persistent horizontal scroll
- [ ] Points column highlighted in destructive color
- [ ] Linked videos section shows with remove buttons
- [ ] Link video form has styled select dropdown

### Forms (Batch 5)
- [ ] Edit form uses card layout with danger zone section
- [ ] Match form stat grid renders responsive (2-4 columns)
- [ ] All forms use `uk-input`/`uk-select`/`uk-textarea`/`uk-form-label`

### Utilities (Batch 6)
- [ ] Clip seeker uses `uk-range` with colored start/end labels
- [ ] Settings tag table renders with rename toggle working
- [ ] Error page centered with large destructive status code
- [ ] `style.css` deleted — no 404 in browser console

### i18n
- [ ] All templates render translations correctly
- [ ] JS translations (`window.TRANSLATIONS`) inject correctly
- [ ] `_()` calls still work in all templates

### JS Behavior
- [ ] `upload.js` works with `UIkit.notification()`
- [ ] `clipper.js` still works (time selection, create button)

### Responsive (375px width)
- [ ] Nav wraps correctly
- [ ] Grid layouts collapse to single column
- [ ] Tables scroll horizontally
- [ ] Forms remain usable

---

## File Change Summary

| # | File | Task | Type of Change |
|---|------|------|----------------|
| 1 | `app/templates/base.html` | 1.1 | Full rewrite — CDN links, theme script, nav with flex layout, Franken UI dropdown |
| 2 | `app/static/css/custom.css` | 1.2 | Update — add seeker labels, video player, page-header, empty-state; keep warning badge |
| 3 | `app/templates/_space_fragment.html` | 1.3 | Class replacement — `space-*` → `uk-badge` variants |
| 4 | `app/templates/upload.html` | 2.1 | Full rewrite — `uk-form-stacked`, `uk-input`, custom file picker |
| 5 | `app/templates/_upload_popup.html` | 2.2 | Simplify — reduce to hidden div |
| 6 | `app/static/js/upload.js` | 2.2 | Rewrite — replace DOM popup with `UIkit.notification()` |
| 7 | `app/templates/index.html` | 3.1 | Class replacement — heading + error alert |
| 8 | `app/templates/_content.html` | 3.2 | Class replacement — filter bar with `uk-btn` |
| 9 | `app/templates/_video_grid.html` | 3.3 | Full rewrite — grid, `uk-card`, badges, empty states |
| 10 | `app/templates/video_detail.html` | 3.4 | Full rewrite — header, player, match context, tags |
| 11 | `app/templates/match_list.html` | 4.1 | Class replacement — heading, buttons, grid, empty state |
| 12 | `app/templates/match_detail.html` | 4.2 | Class replacement — header, notes, section headings |
| 13 | `app/templates/_match_stats.html` | 4.3 | Full rewrite — `uk-table`, header cells, advanced stats |
| 14 | `app/templates/_match_videos.html` | 4.4 | Full rewrite — card items, badges, select form |
| 15 | `app/templates/_match_card.html` | 4.5 | Full rewrite — `uk-card` with hover transition |
| 16 | `app/templates/edit.html` | 5.1 | Full rewrite — card layout, inputs, danger zone |
| 17 | `app/templates/match_form.html` | 5.2 | Full rewrite — form grid, stat grid, textarea |
| 18 | `app/templates/clip.html` | 6.1 | Full rewrite — seeker with `uk-range`, colored labels |
| 19 | `app/templates/settings.html` | 6.2 | Class replacement — card, borders, buttons, inputs |
| 20 | `app/templates/error.html` | 6.3 | Class replacement — layout, text, buttons |
| 21 | `app/static/css/style.css` | 6.4 | **Delete** — fully replaced |

**Total: 18 templates modified + 2 CSS files (+1 updated, -1 deleted) + 1 JS file rewritten**

---

## Execution Order

1. **Batch 1** (3 implementers in parallel): `base.html` + `custom.css` + `_space_fragment.html`
2. **Batch 2** (2 implementers in parallel after Batch 1): `upload.html` + `_upload_popup.html`+`upload.js`
3. **Batch 3** (4 implementers in parallel after Batch 1): `index.html` + `_content.html` + `_video_grid.html` + `video_detail.html`
4. **Batch 4** (5 implementers in parallel after Batch 1): All match system templates
5. **Batch 5** (2 implementers in parallel after Batch 1): `edit.html` + `match_form.html`
6. **Batch 6** (4 implementers in parallel after Batch 1): `clip.html` + `settings.html` + `error.html` + DELETE `style.css`

Batches 3-6 are all independent of each other and can run in parallel after Batch 1 completes. Batch 2 can also run in parallel with Batches 3-6 after Batch 1.
