---
session: ses_1c56
updated: 2026-05-18T10:27:00.609Z
---

# Session Summary

## Goal
Create a detailed micro-task implementation plan for migrating 18 Jinja2 templates + 1 style.css to Franken UI CDN classes (zero backend changes, no build pipeline), saved to `thoughts/shared/plans/2026-05-18-franken-ui-rebuild-plan.md`.

## Constraints & Preferences
- Python/FastAPI app with Jinja2, HTMX, vanilla JS — no npm/node/build pipeline
- Franken UI v2.1.2 via jsDelivr CDN only (`franken-ui.css` includes components + Tailwind utilities + theming)
- All 18 templates must keep existing Jinja2 variables, `_("key")` i18n calls, `hx-*` HTMX attributes, and `upload.js`/`clipper.js` JS files
- Zero Python backend changes — pure template/CSS replacement
- Dark mode via `.dark` class + Franken UI theme system
- Existing `app/static/css/custom.css` (31 lines) gets expanded to ~50 lines with overrides (warning badge, seeker label colors, video player, page-header, empty-state)
- Plan must be structured into micro-tasks with parallel batch groupings and dependency annotations

## Progress

### Done
- [x] Read the design doc at `thoughts/shared/designs/2026-05-18-franken-ui-rebuild-design.md` — confirms 5-phase approach, class mappings per template, CDN integration strategy
- [x] Read all 18 templates (`base.html`, `index.html`, `upload.html`, `_upload_popup.html`, `_content.html`, `_video_grid.html`, `video_detail.html`, `clip.html`, `edit.html`, `settings.html`, `error.html`, `match_list.html`, `match_detail.html`, `match_form.html`, `_match_card.html`, `_match_stats.html`, `_match_videos.html`, `_space_fragment.html`)
- [x] Read current `style.css` (382 lines) — identified all custom classes that need Franken UI equivalents
- [x] Read current `custom.css` (31 lines) — base for the expanded overrides file
- [x] Read `upload.js` (234 lines) — identified inline popup DOM manipulation that needs UIkit.notification() migration
- [x] Researched Franken UI v2.1.2 CDN via Context7 and direct docs — found jsDelivr CDN URLs, component class names, theme system config, notification API (`UIkit.notification({message, status, pos})`), dropdown API (`data-uk-dropdown="mode: click"`), and available components
- [x] Wrote complete plan to `thoughts/shared/plans/2026-05-18-franken-ui-rebuild-plan.md` with:
  - CDN URLs pinned to `[email protected]`
  - 21 file operations across 6 parallel batches with explicit dependency graph
  - Complete replacement HTML/CSS/JS code for each task
  - Class mapping tables showing old→new for every component
  - Verification checklist (backend tests, manual visual, dark mode, responsive)
  - Commit messages per task

### In Progress
- [ ] (none — plan is complete and ready for implementation)

### Blocked
- (none)

## Key Decisions
- **Franken UI v2.1.2 via jsDelivr CDN**: The `franken-ui.css` bundle includes both component styles AND Tailwind utility classes (flex, grid, gap, text-*, bg-*, etc.) — no separate Tailwind install needed. UIkit JS from the same package provides dropdown and notification behaviors. This is the path that satisfies the "no build pipeline" constraint.
- **Dependency graph → 6 parallel batches**: Batch 1 (Foundation) must finish first because `base.html` provides CDN links and `custom.css` provides overrides. Batches 2–6 can all run in parallel after Batch 1 completes. This maximizes implementation velocity.
- **`.page-header` class kept in `custom.css`**: Rather than inlining the responsive flex layout in every template, this utility class handles the video_detail/match_list/match_detail header pattern consistently. The design doc initially proposed `flex justify-between items-start gap-4 mb-1` repeated in each template, but the shared class approach reduces repetition and ensures consistent behavior at 375px.
- **Franken UI dropdown replaces manual lang switcher**: The current `lang-dropdown`/`lang-btn`/`lang-menu` classes plus inline JS are replaced by `data-uk-dropdown="mode: click"` — removing ~20 lines of custom CSS and ~30 lines of JS from base.html
- **UIkit.notification() replaces upload popup DOM**: The current upload.js creates/manages a fixed-position popup div with inline styles. Switching to `UIkit.notification({pos: 'bottom-left'})` removes all popup markup/styles while keeping the same visual position and adding auto-dismiss for success states. Hidden state div + sessionStorage are preserved for HTMX navigation resilience.
- **`uk-range` for clip sliders**: `seeker-slider` class replaced by `uk-range` which is Franken UI's styled range input — consistent with other form controls

## Next Steps
1. **Batch 1 execution** (3 implementers): Implement Task 1.1 (`base.html` — CDN links, theme script, flex nav, Franken UI dropdown), Task 1.2 (`custom.css` — expand with .seeker-label-start/end, .video-player, .page-header, .empty-state), Task 1.3 (`_space_fragment.html` — uk-badge classes)
2. **Batch 2 execution** (2 implementers, after Batch 1): Implement Task 2.1 (`upload.html` — form controls) and Task 2.2 (`_upload_popup.html` + `upload.js` — notification API)
3. **Batches 3–6 execution** (after Batch 1, parallel with each other): Implement all video pages (4 tasks), match system (5 tasks), forms (2 tasks), and utilities+cleanup (4 tasks)
4. **Final verification**: Run `pytest tests/ -v`, check all pages in light/dark mode at mobile/desktop viewports, verify no 404 for deleted style.css

## Critical Context
- **CDN URLs** (production): `https://cdn.jsdelivr.net/npm/[email protected]/dist/css/franken-ui.css`, `https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit.min.js`, `https://cdn.jsdelivr.net/npm/[email protected]/dist/js/uikit-icons.min.js`
- **Theme classes on `<html>`**: `uk-theme-neutral uk-radii-md uk-shadows-sm uk-font-sm` (with `.dark` added for dark mode)
- **Body classes**: `bg-background text-foreground`
- **UIkit.notification() API**: `UIkit.notification({message: string, status: 'primary'|'destructive'|'warning'|'success', pos: 'bottom-left'|'top-center'|..., timeout: milliseconds})`
- **Dropdown API**: `<div class="uk-inline"><button class="uk-btn uk-btn-ghost" type="button">...</button><div class="uk-dropdown" data-uk-dropdown="mode: click">...</div></div>`
- **Key Franken UI classes used**: `uk-btn uk-btn-primary uk-btn-destructive uk-btn-ghost uk-btn-sm`, `uk-card uk-card-body uk-card-title`, `uk-table uk-table-sm uk-table-divider`, `uk-input uk-form-sm uk-form-lg`, `uk-select`, `uk-textarea`, `uk-form-stacked uk-form-label`, `uk-badge uk-badge-primary uk-badge-destructive`, `uk-range`, `uk-alert uk-alert-destructive`, `uk-container`, `uk-close`, `uk-h2 uk-h3 uk-h4`, `uk-inline`, `uk-dropdown`, `uk-nav uk-nav-dropdown uk-overflow-auto`
- **Custom CSS overrides kept** (4 groups): `.uk-badge-warning` (space indicator warning color), `.seeker-label-start`/`.seeker-label-end` (clip tool colors using `hsl(var(--primary))`/`hsl(var(--destructive))`), `.video-player video` (black background + responsive heights), `.page-header` (responsive flex row), `.empty-state` (centered muted text)
- **`style.css` is fully replaced** — all 382 lines eliminated. No `btn`, `error`, `space-*`, `*card*`, `seeker-*`, `match-*`, `stats-*`, `lang-*` classes remain.
- **Existing plan file** was at `thoughts/shared/plans/2026-05-18-franken-ui-rebuild-plan.md` — already had structure but used `@latest` CDN URLs and lacked proper micro-task batching with dependency annotations. Complete rewrite with corrected URLs and task structure completed this session.
- **21 file operations defined** across 6 batches: 18 templates (full rewrites or targeted class replacements) + 2 CSS files (custom.css expanded, style.css deleted) + 1 JS file (upload.js rewritten for notification API)

## File Operations

### Read
- `/home/franz/project/video-bank/thoughts/shared/designs/2026-05-18-franken-ui-rebuild-design.md`
- `/home/franz/project/video-bank/thoughts/shared/plans/2026-05-18-franken-ui-rebuild-plan.md` (pre-existing, 637 lines, restructured this session)
- `/home/franz/project/video-bank/app/templates/base.html`
- `/home/franz/project/video-bank/app/templates/index.html`
- `/home/franz/project/video-bank/app/templates/upload.html`
- `/home/franz/project/video-bank/app/templates/_upload_popup.html`
- `/home/franz/project/video-bank/app/templates/_content.html`
- `/home/franz/project/video-bank/app/templates/_video_grid.html`
- `/home/franz/project/video-bank/app/templates/video_detail.html`
- `/home/franz/project/video-bank/app/templates/clip.html`
- `/home/franz/project/video-bank/app/templates/edit.html`
- `/home/franz/project/video-bank/app/templates/settings.html`
- `/home/franz/project/video-bank/app/templates/error.html`
- `/home/franz/project/video-bank/app/templates/match_list.html`
- `/home/franz/project/video-bank/app/templates/match_detail.html`
- `/home/franz/project/video-bank/app/templates/match_form.html`
- `/home/franz/project/video-bank/app/templates/_match_card.html`
- `/home/franz/project/video-bank/app/templates/_match_stats.html`
- `/home/franz/project/video-bank/app/templates/_match_videos.html`
- `/home/franz/project/video-bank/app/templates/_space_fragment.html`
- `/home/franz/project/video-bank/app/static/css/style.css`
- `/home/franz/project/video-bank/app/static/css/custom.css`
- `/home/franz/project/video-bank/app/static/js/upload.js`
- `/home/franz/project/video-bank/app/routes/matches.py` (for match_form.html context)

### Modified
- `/home/franz/project/video-bank/thoughts/shared/plans/2026-05-18-franken-ui-rebuild-plan.md` — Complete rewrite with micro-task structure, parallel batches, corrected CDN URLs (v2.1.2 pinned), full replacement code per task, dependency graph, commit messages, verification checklist, and file change summary (21 file operations across 6 batches)
