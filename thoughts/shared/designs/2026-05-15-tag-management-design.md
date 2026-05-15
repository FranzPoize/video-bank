---
date: 2026-05-15
topic: "Tag Management — Settings page with tag CRUD"
status: draft
---

## Problem Statement

Users need a settings page to manage tags independently of videos. Currently tags can only be created/edited through the video upload/edit forms. There's no way to rename an existing tag or delete a tag system-wide.

## Constraints

- Make code as simple as possible
- Code should be testable
- Avoid inversion of control as much as possible
- Make unit tests for the app
- Follow existing patterns: HTMX for dynamic UI, server-rendered HTML
- CSS in `base.html` `<style>` blocks (no separate CSS files)
- All existing tests must remain passing

## Existing Tag Infrastructure (Analysis)

### Database Schema

**`tags` table:**
```sql
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
```

**`video_tags` junction table:**
```sql
CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(video_id, tag_id)
);
```

**Key existing behavior:**
- `ON DELETE CASCADE` on both foreign keys
- When a **video** is deleted → its `video_tags` rows are auto-removed
- When a **tag** is deleted → its `video_tags` rows are auto-removed
- `tags.name` is `UNIQUE` — duplicate tag names prevented at DB level

### Existing Service Functions (`app/services/tag_service.py`)

| Function | Purpose |
|----------|---------|
| `get_or_create_tag(db, name)` | Find by name (lowercased), create if missing. Returns tag id. |
| `list_all_tags(db)` | Return all tags ordered by name (id + name). |
| `get_video_tags(db, video_id)` | Return tag **names** for a video. |
| `set_video_tags(db, video_id, tag_names)` | **Replace** all tags on a video. Deletes existing associations, inserts new ones. |

### Existing Routes

| Route | Purpose |
|-------|---------|
| `GET /api/tags` | Return all tags as JSON array of names. |
| `GET /?tag_id=X` | Filter videos by tag id (via query param). |

### Existing UI

- Tag filter bar (`_content.html`) — buttons for each tag, HTMX-powered filtering
- Tag badges on video cards (`_video_grid.html`) and detail page (`video_detail.html`) — plain text, not clickable
- Tag input on upload (`upload.html`) and edit (`edit.html`) — comma-separated text input

## Approach

**Minimal design following existing patterns:**

1. **Settings page** (`GET /settings`) — lists all tags with usage counts
2. **Service layer additions** to `tag_service.py`:
   - `get_tag(db, tag_id)` — fetch single tag
   - `update_tag(db, tag_id, new_name)` — rename tag (handles UNIQUE)
   - `delete_tag(db, tag_id)` — delete tag (CASCADE handles associations)
   - `list_all_tags_with_counts(db)` — tags with video usage counts
3. **Route additions** (`app/routes/tags.py`):
   - `GET /settings` — settings page
   - `POST /api/tags/{tag_id}/rename` — rename tag
   - `POST /api/tags/{tag_id}/delete` — delete tag
4. **UI additions:**
   - "Settings" link in nav bar (`base.html`)
   - `settings.html` template with tag list + rename/delete actions

**Alternatives considered:**
- Modal-based rename form — rejected in favor of inline toggle (simpler, no JS complexity)
- PUT/DELETE HTTP methods for API — rejected in favor of POST (HTML forms don't support PUT/DELETE natively)
- Separate "Tags" page vs. "Settings" page — requirements specify "settings page", so using `/settings`

## Architecture

```
Nav bar (base.html)
  [Video Bank] [Upload] [Settings] [space-indicator] [🌐 EN ▼]
                                 │
                                 ▼
                        GET /settings
                                 │
                                 ▼
              settings.html template (tag management)
    ┌─────────────────────────────────────────────────────────┐
    │  Tag Management                                          │
    │                                                          │
    │  ┌───────────────────────────────────────────────────┐  │
    │  │  Name                     Videos  Actions          │  │
    │  ├───────────────────────────────────────────────────┤  │
    │  │  tutorial                 [5]     [Rename] [Del] │  │
    │  │  funny                    [3]     [Rename] [Del] │  │
    │  │  demo                     [2]     [Rename] [Del] │  │
    │  └───────────────────────────────────────────────────┘  │
    │                                                          │
    │  [Rename] toggles inline form:                          │
    │  ┌─────────────────────────────────────────┐           │
    │  │  [tutorial_____] [Save] [Cancel]       │           │
    │  └─────────────────────────────────────────┘           │
    │                                                          │
    │  [Del] triggers: confirm("Delete tag 'X'?")            │
    └─────────────────────────────────────────────────────────┘
```

## Components

### 1. Service Layer Additions (`app/services/tag_service.py`)

#### `get_tag(db, tag_id: int) -> dict | None`

Fetch a single tag by id. Returns `None` if not found.

```python
async def get_tag(db, tag_id: int) -> dict | None:
    """Fetch a single tag by id. Returns None if not found."""
    cursor = await db.execute("SELECT id, name FROM tags WHERE id = ?", (tag_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None
```

#### `update_tag(db, tag_id: int, new_name: str) -> dict`

Rename a tag. Normalizes the name (strip + lowercase).

**Error cases:**
- Empty name after stripping → `ValueError("Tag name cannot be empty.")`
- Name already exists for different tag → `ValueError("A tag with this name already exists.")`

**Flow:**
1. Normalize: `new_name.strip().lower()`
2. Check if empty → raise
3. Check if name exists for different tag → raise
4. `UPDATE tags SET name = ? WHERE id = ?`
5. Return updated tag via `get_tag()`

#### `delete_tag(db, tag_id: int) -> bool`

Delete a tag by id. Returns `True` if deleted, `False` if not found.

**Important:** The `ON DELETE CASCADE` on `video_tags.tag_id` automatically removes all tag-to-video associations when a tag is deleted. This is handled by SQLite, no additional code needed.

```python
async def delete_tag(db, tag_id: int) -> bool:
    """Delete a tag. Returns True if deleted, False if not found.
    
    ON DELETE CASCADE in schema handles video_tags cleanup.
    """
    cursor = await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    await db.commit()
    return cursor.rowcount > 0
```

#### `list_all_tags_with_counts(db) -> list[dict]`

List all tags with video usage counts. Ordered by name.

```python
async def list_all_tags_with_counts(db) -> list[dict]:
    """List all tags with video usage counts. Ordered by name."""
    cursor = await db.execute("""
        SELECT t.id, t.name, COUNT(vt.video_id) as video_count
        FROM tags t
        LEFT JOIN video_tags vt ON t.id = vt.tag_id
        GROUP BY t.id
        ORDER BY t.name
    """)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
```

### 2. Route Additions (`app/routes/tags.py`)

Import the shared `templates` from `app.templates` (i18n-ready).

#### `GET /settings`

Settings page displaying tag management.

```python
@router.get("/settings")
async def settings_page(request: Request, db=Depends(get_db)):
    """Settings page with tag management."""
    i18n = getattr(request.state, "i18n", get_i18n_context(DEFAULT_LANG))
    tags = await tag_service.list_all_tags_with_counts(db)
    return templates.TemplateResponse(
        request, "settings.html",
        {
            **i18n,
            "tags": tags,
        },
    )
```

#### `POST /api/tags/{tag_id}/rename`

Rename a tag. Accepts form-encoded `new_name` parameter.

**Redirects on success:** Back to `/settings`
**Error handling:** On `ValueError`, redirect with `?error=...` query param

```python
@router.post("/api/tags/{tag_id}/rename")
async def rename_tag(
    request: Request,
    tag_id: int,
    new_name: str = Form(...),
    db=Depends(get_db),
):
    """Rename a tag. Redirects back to settings."""
    try:
        await tag_service.update_tag(db, tag_id, new_name)
        return RedirectResponse(url="/settings", status_code=303)
    except ValueError as e:
        # Pass error via query param for template to display
        error_code = "empty" if "empty" in str(e).lower() else "duplicate"
        return RedirectResponse(
            url=f"/settings?error={error_code}",
            status_code=303,
        )
```

#### `POST /api/tags/{tag_id}/delete`

Delete a tag.

```python
@router.post("/api/tags/{tag_id}/delete")
async def delete_tag_route(
    tag_id: int,
    db=Depends(get_db),
):
    """Delete a tag. Redirects back to settings."""
    await tag_service.delete_tag(db, tag_id)
    return RedirectResponse(url="/settings", status_code=303)
```

### 3. UI Additions

#### Nav bar (`base.html`)

Add "Settings" link after "Upload":

```html
<nav>
    <a href="/">{{ _("nav.video_bank") }}</a>
    <a href="/upload">{{ _("nav.upload") }}</a>
    <a href="/settings">{{ _("nav.settings") }}</a>
    ...
</nav>
```

#### Settings Template (`app/templates/settings.html`)

Extends `base.html`. Displays tags in a simple list with:
- Tag name
- Video count
- Rename button (toggles inline form)
- Delete button (with JS confirm)

**Key behaviors:**
- Click **[Rename]** → Hides button, shows inline form with current name pre-filled
- Click **[Save]** → Submits form to `/api/tags/{id}/rename`
- Click **[Cancel]** → Hides form, shows buttons again
- Click **[Delete]** → `return confirm("Delete tag 'X'?")` before submitting

**Error display:** Reads `error` query param and shows appropriate message.

### 4. i18n Additions

Add to `translations/en.json`:

```json
{
  "nav.settings": "Settings",
  "page.settings": "Settings",
  "tag_management": "Tag Management",
  "tag.name": "Name",
  "tag.videos": "Videos",
  "tag.actions": "Actions",
  "tag.rename": "Rename",
  "tag.delete": "Delete",
  "tag.save": "Save",
  "tag.cancel": "Cancel",
  "tag.confirm_delete": "Delete this tag? Videos tagged with it will lose this tag.",
  "tag.no_tags": "No tags yet. Tags are created when uploading videos.",
  "tag.error.duplicate": "A tag with this name already exists.",
  "tag.error.empty": "Tag name cannot be empty."
}
```

Add to `translations/fr.json` (French translations):

```json
{
  "nav.settings": "Paramètres",
  "page.settings": "Paramètres",
  "tag_management": "Gestion des étiquettes",
  "tag.name": "Nom",
  "tag.videos": "Vidéos",
  "tag.actions": "Actions",
  "tag.rename": "Renommer",
  "tag.delete": "Supprimer",
  "tag.save": "Enregistrer",
  "tag.cancel": "Annuler",
  "tag.confirm_delete": "Supprimer cette étiquette ? Les vidéos associées perdront cette étiquette.",
  "tag.no_tags": "Aucune étiquette pour le moment. Les étiquettes sont créées lors du téléversement de vidéos.",
  "tag.error.duplicate": "Une étiquette avec ce nom existe déjà.",
  "tag.error.empty": "Le nom de l'étiquette ne peut pas être vide."
}
```

## Data Flow

### View Settings Page

```
User navigates to /settings
  │
  ▼
GET /settings
  │
  ▼
list_all_tags_with_counts(db)
  │
  ▼
SQL: LEFT JOIN tags + video_tags + COUNT
  │
  ▼
settings.html renders tag list
  │
  ▼
User sees: tutorial [5] [Rename] [Delete]
           funny    [3] [Rename] [Delete]
```

### Rename Tag Flow

```
User clicks [Rename] on "tutorial"
  │
  ▼
JS toggles: hide buttons, show form
  │
  ▼
Form appears with pre-filled: "tutorial"
  │
  ▼
User changes to "training", clicks [Save]
  │
  ▼
POST /api/tags/{id}/rename  new_name=training
  │
  ▼
update_tag():
  ├── Normalize: "training" → "training"
  ├── Check UNIQUE: not in use
  └── UPDATE tags SET name = 'training' WHERE id = ?
  │
  ▼
RedirectResponse to /settings
  │
  ▼
Page reloads with updated tag name
```

### Delete Tag Flow

```
User clicks [Delete] on "tutorial"
  │
  ▼
onsubmit="return confirm('Delete tag 'tutorial'?')"
  │
  ├── User clicks "Cancel" → form not submitted
  │
  └── User clicks "OK" → form submits
        │
        ▼
POST /api/tags/{id}/delete
  │
  ▼
delete_tag(): DELETE FROM tags WHERE id = ?
  │
  ▼
SQLite ON DELETE CASCADE auto-removes video_tags rows
  │
  ▼
RedirectResponse to /settings
  │
  ▼
Page reloads — tag is gone from list
```

## Error Handling

| Scenario | Service Layer | Route Layer | UI Layer |
|----------|---------------|-------------|----------|
| Rename to empty string | Raises `ValueError("...empty...")` | Redirects with `?error=empty` | Shows "Tag name cannot be empty." |
| Rename to existing name | Raises `ValueError("...duplicate...")` | Redirects with `?error=duplicate` | Shows "A tag with this name already exists." |
| Delete non-existent tag | Returns `False` | Redirects anyway | No visible change (tag was already gone) |
| Tag has video associations | — | — | `ON DELETE CASCADE` handles cleanup automatically |

**Important:** Deleting a tag **does NOT delete any videos**. It only removes:
1. The tag row from `tags` table
2. The tag-to-video association rows from `video_tags` table (via CASCADE)

Videos remain intact, they just lose that particular tag.

## Testing Strategy

### New tests in `tests/test_tags.py`:

| Test | Purpose |
|------|---------|
| `test_get_tag` | Fetch single tag by id |
| `test_rename_tag_success` | Successfully rename a tag |
| `test_rename_tag_duplicate` | Rename to existing name raises error |
| `test_rename_tag_empty` | Rename to empty raises error |
| `test_delete_tag` | Delete tag, verify it's removed |
| `test_delete_tag_cascades` | Delete tag, verify `video_tags` rows removed |
| `test_list_tags_with_counts` | Verify counts are correct |
| `test_settings_page` | GET `/settings` returns 200 with tags |
| `test_rename_tag_route` | POST rename endpoint works |
| `test_delete_tag_route` | POST delete endpoint works |

### Key test scenarios:

**Tag delete cascade test:**
```python
# 1. Create video with tags
# 2. Verify video_tags rows exist
# 3. Delete a tag
# 4. Verify video_tags row for that tag is gone
# 5. Verify video still exists (not deleted)
```

**Rename duplicate test:**
```python
# 1. Create two tags: "tag1", "tag2"
# 2. Try to rename "tag2" to "tag1"
# 3. Expect ValueError
```

## Implementation Checklist

### Phase 1: Service Layer
- [ ] Add `get_tag(db, tag_id)` to `tag_service.py`
- [ ] Add `update_tag(db, tag_id, new_name)` to `tag_service.py`
- [ ] Add `delete_tag(db, tag_id)` to `tag_service.py`
- [ ] Add `list_all_tags_with_counts(db)` to `tag_service.py`
- [ ] Run existing tests to verify no regressions

### Phase 2: Routes
- [ ] Update `app/routes/tags.py` to import shared `templates`
- [ ] Add `GET /settings` route
- [ ] Add `POST /api/tags/{tag_id}/rename` route
- [ ] Add `POST /api/tags/{tag_id}/delete` route
- [ ] Run existing tests

### Phase 3: UI
- [ ] Add translation keys to `translations/en.json` and `translations/fr.json`
- [ ] Add "Settings" link to `base.html` nav bar
- [ ] Create `app/templates/settings.html` with tag list
- [ ] Add inline rename form toggle (simple JS)
- [ ] Add delete confirmation (`onsubmit="return confirm(...)"`)
- [ ] Manual verification: visit `/settings`, rename a tag, delete a tag

### Phase 4: Tests
- [ ] Add `test_get_tag`
- [ ] Add `test_rename_tag_success`
- [ ] Add `test_rename_tag_duplicate`
- [ ] Add `test_rename_tag_empty`
- [ ] Add `test_delete_tag`
- [ ] Add `test_delete_tag_cascades`
- [ ] Add `test_list_tags_with_counts`
- [ ] Add `test_settings_page`
- [ ] Add `test_rename_tag_route`
- [ ] Add `test_delete_tag_route`
- [ ] Run all tests: `pytest -q`

## Open Questions

1. **Bulk operations:** Delete all unused tags? Not in requirements, could add later if needed.

2. **Tag autocomplete:** The requirements don't mention this, but it would be a nice UX improvement (users must currently type exact tag names). Out of scope for this feature.

3. **Clickable tags on video cards:** Currently tags are plain text. Making them clickable (link to `/?tag_id=X`) would be a UX improvement. Out of scope.

4. **Usage threshold:** Should we prevent deletion of tags with many videos? The requirements don't specify this, so allowing delete with just a confirmation is fine.
