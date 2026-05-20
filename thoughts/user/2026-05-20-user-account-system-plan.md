# User Account System Implementation Plan

Source request: `thoughts/user/user-account-system.md`
Validated design: `thoughts/shared/designs/2026-05-20-user-account-system-design.md`

## Goal

Add users, accounts, per-account rights, email verification, invitations, and account isolation for videos, matches, tags, clips, and settings while keeping the existing FastAPI + Jinja2 + HTMX + SQLite architecture simple and testable.

## Mandatory executor rule

The executor must stop at every checkpoint line that says:

`CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !`

At each stop, report what was completed, what tests passed, what remains, and any user-facing behavior that should be validated before continuing.

## Technology choices for this implementation

Use the existing stack by default:

- FastAPI routes and dependencies.
- Jinja2 templates with the existing translation context.
- HTMX for form/fragment interactions where useful.
- Vanilla JavaScript only if a page needs client behavior.
- SQLite with raw SQL migrations in `app/database.py`.
- Service functions in `app/services/`, always taking `db` as the first argument.
- Pytest + pytest-asyncio + httpx tests.

Chosen additions:

- Password hashing: Python standard library `hashlib.pbkdf2_hmac` plus `secrets` and per-password random salts. This avoids adding a dependency and is adequate for this small self-hosted app if implemented with a strong iteration count.
- Session storage: opaque random session tokens stored hashed in SQLite, sent as an HttpOnly cookie.
- Email boundary: an `email_service` with deterministic console/log behavior for development and tests first, plus SMTP environment configuration later if desired.

Items still needing user/product decision during implementation:

- Production email provider selection: You should discuss this with the user when you implement it
- Exact initial administrator selection for existing installations during migration: You should discuss this with the user when you implement it
- Whether password reset belongs in the first release after invitation support: You should discuss this with the user when you implement it

## Implementation conventions to follow

- Keep business logic in explicit service modules; avoid inversion of control.
- Use snake_case modules/functions and full `app.xxx` imports.
- Use parameterized SQL only.
- New route modules must use `APIRouter`, spread `**i18n` into template contexts, and redirect after POST with status code `303`.
- Service validation errors should raise `ValueError`; infrastructure failures should raise `RuntimeError`; not-found decisions belong in routes.
- Every checkpoint must include unit/service tests and route tests for the user-visible behavior introduced in that checkpoint.
- All new user-facing strings must be added to both `translations/en.json` and `translations/fr.json`.

---

## Checkpoint 1 — Authentication foundation and database schema

### Outcome

The database can represent users, accounts, memberships, capabilities, sessions, email verification tokens, and invitations. Core auth/account/permission service functions exist and are tested directly, but routes can still be mostly unchanged.

### Files to create

- `app/services/security_service.py`
- `app/services/auth_service.py`
- `app/services/account_service.py`
- `app/services/permission_service.py`
- `app/services/session_service.py`
- `app/services/email_service.py`
- `tests/test_security_service.py`
- `tests/test_auth_service.py`
- `tests/test_account_service.py`
- `tests/test_permission_service.py`
- `tests/test_session_service.py`
- `tests/test_email_service.py`

### Files to modify

- `app/database.py`
- `app/main.py`
- `tests/conftest.py`
- `requirements.txt` only if the implementer chooses not to use stdlib password hashing. Prefer no new dependency.

### Database work

Add migration version `6` with these tables and indexes:

- `users`: email, normalized email, password hash, email verification status, timestamps.
- `accounts`: display name and timestamps.
- `account_memberships`: user/account link, capability flags, timestamps, revoked/active marker.
- `sessions`: hashed session token, user id, active account id, expiry, revoked timestamp, timestamps.
- `email_verification_tokens`: hashed token, user id, expiry, used timestamp.
- `invitations`: account id, invited email, inviter id, selected capabilities, hashed token, expiry, accepted/revoked timestamps.

Use SQLite-friendly integer booleans for capability flags. Create indexes for normalized email, token hashes, session token hashes, account membership lookups, and invitation state.

### Service work

- `security_service.py`: normalize emails, hash/verify passwords, create random tokens, hash tokens before storage, compare safely.
- `auth_service.py`: create unverified users, reject duplicate normalized emails with a safe generic error, validate login credentials, reject unverified login.
- `account_service.py`: create accounts, create the first admin membership, list accounts for a user, set/get active account ids.
- `permission_service.py`: define capability constants and default presets, check memberships, check capabilities, prevent removing the last administrator.
- `session_service.py`: create, load, revoke, and expire sessions.
- `email_service.py`: deterministic test-safe email send boundary returning structured send results.

Chosen default capability names:

- `manage_videos`
- `manage_matches`
- `manage_tags`
- `manage_account_settings`
- `manage_members`
- `admin`

`admin` is a persisted capability flag and means all capabilities. UI presets can be added later without changing the authorization decision.

### Tests

- Password hashes are salted and verify correctly.
- Duplicate email signup is rejected safely.
- Unverified users cannot login.
- Verification tokens are stored hashed and expire.
- Signup verification can create an account and admin membership after email verification.
- Session tokens are stored hashed, can be loaded, expire, and can be revoked.
- Permission checks allow admins and reject non-members.
- Last-admin protection rejects removing or demoting the only admin.
- Email service does not send real email during tests.

### Validation before stopping

Run:

- `pytest tests/test_security_service.py tests/test_auth_service.py tests/test_account_service.py tests/test_permission_service.py tests/test_session_service.py tests/test_email_service.py`
- `pytest tests/test_videos.py tests/test_tags.py tests/test_matches.py tests/test_clips.py`

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Checkpoint 2 — Signup, email verification, login, logout, and authenticated layout

### Outcome

Users can sign up, receive a verification flow, verify their email, then login/logout. Direct signup creates the account only after successful email verification, matching the validated design.

### Files to create

- `app/routes/auth.py`
- `app/dependencies.py`
- `app/templates/signup.html`
- `app/templates/login.html`
- `app/templates/verify_email.html`
- `tests/test_auth_routes.py`
- `tests/test_auth_dependencies.py`

### Files to modify

- `app/main.py`
- `app/templates/base.html`
- `translations/en.json`
- `translations/fr.json`
- `tests/conftest.py` if helper fixtures are useful.

### Route work

- `GET /signup`: render signup form.
- `POST /signup`: create unverified user and verification token, send verification email through `email_service`, show confirmation page.
- `GET /verify-email?token=...`: verify token, mark user verified, create initial account and admin membership if this was direct signup, show success/failure result.
- `GET /login`: render login form.
- `POST /login`: validate credentials, require verified email, create session cookie, choose default active account, redirect to `/`.
- `POST /logout`: revoke the current session, clear cookie, redirect to login.

### Dependency work

- `get_current_user_optional(request, db)` for layout and public pages.
- `require_current_user(request, db)` for protected pages.
- `require_active_account(request, db)` to resolve current account and membership.
- Cookie settings: HttpOnly, SameSite=Lax, secure when configured for production.

### Template/layout work

- Show login/signup links for anonymous users.
- Show account/user indicator and logout for authenticated users.
- Use translation keys for all labels, errors, and page titles.
- Keep forms simple, server-rendered, and usable without JavaScript.

### Tests

- Signup form renders.
- Signup creates unverified user and token.
- Verification with valid token activates user and creates account/admin membership.
- Invalid/expired verification token renders safe failure.
- Login rejects unknown email and wrong password with the same user-facing error.
- Login rejects unverified email and offers resend path placeholder.
- Login creates session cookie.
- Logout revokes session and clears cookie.
- Base layout changes navigation based on auth state.

### Validation before stopping

Run:

- `pytest tests/test_auth_routes.py tests/test_auth_dependencies.py tests/test_auth_service.py tests/test_account_service.py tests/test_session_service.py`
- Manually verify: signup page, verification result page, login, logout, and translated labels in English/French.

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Checkpoint 3 — Protect existing pages and add account context

### Outcome

Existing videos, matches, tags, clips, uploads, and settings pages require authentication and operate inside the active account context. Existing single-user behavior remains available after migration to a default account.

### Files to modify

- `app/database.py`
- `app/main.py`
- `app/routes/videos.py`
- `app/routes/matches.py`
- `app/routes/tags.py`
- `app/services/video_service.py`
- `app/services/match_service.py`
- `app/services/tag_service.py`
- `app/services/clip_service.py`
- `app/templates/base.html`
- `app/templates/index.html`
- `app/templates/_content.html`
- `app/templates/_video_grid.html`
- `app/templates/video_detail.html`
- `app/templates/upload.html`
- `app/templates/edit.html`
- `app/templates/clip.html`
- `app/templates/settings.html`
- `app/templates/match_list.html`
- `app/templates/match_detail.html`
- `app/templates/match_form.html`
- `app/templates/_match_card.html`
- `app/templates/_match_videos.html`
- `tests/conftest.py`
- Existing route/service tests that assume anonymous access.

### Database work

Add migration version `7`:

- Add `account_id` to `videos`.
- Add `account_id` to `matches`.
- Add `account_id` to `tags`.
- Replace global tag uniqueness with per-account uniqueness where SQLite migration allows. If SQLite cannot alter the existing unique constraint in place safely, create a new table and copy data in the migration.
- Add account-aware indexes for videos, matches, tags, and join tables.

Migration strategy for current installations:

- Create or require one default account for existing rows.
- Attach existing videos, matches, and tags to that account.
- Assign an initial administrator before enforcing login-only access.
- Exact initial administrator selection for existing installations during migration: You should discuss this with the user when you implement it

### Service work

- Add `account_id` parameters to account-scoped video, match, tag, and clip service functions.
- Every read must filter by `account_id`.
- Every create must write `account_id`.
- Every update/delete/link/unlink must verify the target row belongs to `account_id`.
- Cross-account ids should behave like not-found, not forbidden, to avoid leaking resource existence.

### Route work

- Require authenticated user and active account for all existing application pages except health, login, signup, verification, and static assets.
- Check capabilities before mutations:
  - Upload/edit/delete/cut/clip video: `manage_videos` or `admin`.
  - Create/edit/delete/link/unlink matches: `manage_matches` or `admin`.
  - Rename/delete tags: `manage_tags` or `admin`.
  - Settings page access: allow read for authenticated account members; show management controls based on capabilities.
- Preserve current URLs where possible.

### Tests

- Anonymous access to protected pages redirects to login.
- Authenticated account member sees only their account's videos, matches, and tags.
- Cross-account video/match/tag ids return not-found or forbidden according to route type without leaking data.
- Users lacking capabilities cannot mutate videos/matches/tags.
- Existing video, tag, match, and clip tests are updated to create authenticated fixtures and active accounts.
- Migration assigns existing rows to a default account.

### Validation before stopping

Run:

- `pytest tests/test_videos.py tests/test_tags.py tests/test_matches.py tests/test_clips.py`
- `pytest tests/test_auth_routes.py tests/test_auth_dependencies.py tests/test_permission_service.py`
- Manual smoke test: login, upload video, tag it, create match, attach video, view all lists as the account admin.

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Checkpoint 4 — Account switcher and account settings

### Outcome

Users with multiple account memberships can see and switch active accounts. Admin users can edit account metadata and view member lists.

### Files to create

- `app/routes/accounts.py`
- `app/templates/account_settings.html`
- `app/templates/_account_switcher.html`
- `app/templates/members.html`
- `tests/test_account_routes.py`

### Files to modify

- `app/main.py`
- `app/templates/base.html`
- `app/services/account_service.py`
- `app/services/permission_service.py`
- `translations/en.json`
- `translations/fr.json`

### Route work

- `GET /accounts`: list available accounts if useful, otherwise redirect to account settings/current account.
- `POST /accounts/switch`: validate membership and update active account in session.
- `GET /account/settings`: show account metadata and member summary.
- `POST /account/settings`: update account display name with `manage_account_settings` or `admin`.
- `GET /account/members`: show members and their current capabilities.

### UI work

- Add account switcher to `base.html` only when the user has more than one active account.
- If the first implementation hides account switching unless needed, still keep backend support complete.
- Use permission-gated controls so non-admin members can see account context but not edit restricted fields.

### Tests

- User with one account does not need to switch.
- User with multiple accounts can switch only to accounts where they have active membership.
- Forged account switch target is rejected.
- Account setting edits require the correct capability.
- Member list requires membership and hides/shows controls based on capabilities.

### Validation before stopping

Run:

- `pytest tests/test_account_routes.py tests/test_account_service.py tests/test_permission_service.py`
- Manual smoke test: create two accounts in tests/fixtures or via service shell, switch active account, confirm lists change.

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Checkpoint 5 — Invitations and membership management

### Outcome

Account admins can invite users by email, choose capabilities, revoke pending invites, and let invited users accept. Existing verified users can accept directly; new users are guided through signup and verification before membership activation.

### Files to create

- `app/services/invitation_service.py`
- `app/routes/invitations.py`
- `app/templates/invite_form.html`
- `app/templates/invitation_accept.html`
- `app/templates/invitation_result.html`
- `app/templates/member_rights.html`
- `tests/test_invitation_service.py`
- `tests/test_invitation_routes.py`
- `tests/test_member_management_routes.py`

### Files to modify

- `app/main.py`
- `app/services/auth_service.py`
- `app/services/account_service.py`
- `app/services/permission_service.py`
- `app/services/email_service.py`
- `app/templates/members.html`
- `translations/en.json`
- `translations/fr.json`

### Service work

- Create invitations with account id, invited normalized email, inviter id, capabilities, hashed token, expiry.
- Revoke invitations.
- Accept invitations:
  - Existing verified matching user: create/update active membership.
  - Existing unverified matching user: require verification before activating membership.
  - New user: route them to signup with invitation context, then verify email, then activate membership.
- Reject expired, revoked, already accepted, or email-mismatched invitations.
- Prevent capability changes that remove the last admin.

### Route work

- `GET /account/invitations/new`: render invite form.
- `POST /account/invitations`: create invite and send email.
- `POST /account/invitations/{invitation_id}/revoke`: revoke pending invite.
- `GET /invitations/accept?token=...`: render accept flow.
- `POST /invitations/accept`: accept for existing verified user or continue to signup/verification.
- `GET /account/members/{membership_id}/rights`: edit member rights.
- `POST /account/members/{membership_id}/rights`: save member rights.
- `POST /account/members/{membership_id}/remove`: remove member with last-admin protection.

### Tests

- Admin can create invitation with selected capabilities.
- Non-admin/member without `manage_members` cannot invite.
- Email send failure keeps consistent pending state and logs the failure.
- Expired/revoked/used invitations show safe errors.
- Existing verified user accepts and receives capabilities.
- New user accepts after signup and email verification.
- Rights editor updates capabilities.
- Removing or demoting the last admin is rejected.

### Validation before stopping

Run:

- `pytest tests/test_invitation_service.py tests/test_invitation_routes.py tests/test_member_management_routes.py`
- `pytest tests/test_auth_routes.py tests/test_account_routes.py tests/test_permission_service.py`
- Manual smoke test: admin invites user, invited user accepts, admin changes rights, permission-gated controls update.

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Checkpoint 6 — Security regression hardening and final UX polish

### Outcome

The system has explicit security regression coverage for stale sessions, revoked memberships, forged account ids, cross-account resource ids, and permission-gated UI. The UI is translated and understandable.

### Files to create

- `tests/test_account_isolation.py`
- `tests/test_security_regressions.py`

### Files to modify

- `app/dependencies.py`
- `app/services/session_service.py`
- `app/services/permission_service.py`
- `app/routes/videos.py`
- `app/routes/matches.py`
- `app/routes/tags.py`
- `app/routes/accounts.py`
- `app/routes/invitations.py`
- `app/templates/base.html`
- `app/templates/error.html`
- `translations/en.json`
- `translations/fr.json`
- Any tests that need clearer authenticated fixtures.

### Hardening work

- Ensure revoked membership invalidates access on the next request.
- Ensure revoked/expired session clears the cookie and redirects to login.
- Ensure active account in session is ignored if the user no longer has membership.
- Ensure every account-scoped domain service filters by account id.
- Ensure mutation routes check capability before reading/mutating sensitive resource data where possible.
- Ensure not-found responses do not reveal cross-account resource existence.
- Ensure all invitation and verification tokens are one-time use and stored hashed only.

### UX polish

- Review all new pages for consistent navigation, form errors, and success messages.
- Add translated empty states for members/invitations.
- Add clear instructions for email verification and invitation acceptance.
- Keep password reset out of scope unless the parent agent/user explicitly asks for it now. Password reset first-release inclusion: You should discuss this with the user when you implement it

### Tests

- Cross-account video/match/tag reads and writes are blocked.
- Forged active account/session values are rejected.
- Revoked membership loses access immediately on next request.
- Revoked session cannot be reused.
- Expired verification/invitation/session tokens are rejected.
- Permission-gated controls do not render for users without required capabilities.
- Full regression suite passes.

### Validation before stopping

Run:

- `pytest`
- Manual end-to-end smoke test as two users in two accounts:
  1. User A signs up and verifies email.
  2. User A uploads a video, creates tags, creates a match.
  3. User A invites User B with limited rights.
  4. User B accepts and confirms only permitted controls/actions are available.
  5. User B cannot access User A resources outside the invited account or perform denied mutations.

CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !

---

## Suggested implementation order inside each checkpoint

1. Write/adjust tests first for the checkpoint behavior.
2. Confirm those tests fail for the intended reason.
3. Implement schema/service changes.
4. Implement route/template changes.
5. Add translations.
6. Run the checkpoint verification commands.
7. Stop exactly at the checkpoint phrase and report to the parent agent.

## Final acceptance criteria

- New users cannot access the app until email verification succeeds.
- Direct signup creates a new account and makes the verified user its admin.
- Admins can invite users to an account and choose rights.
- Users can have rights in more than one account.
- Videos, matches, tags, clips, and settings are account-scoped.
- Cross-account data never appears in lists, detail pages, streams, tags, match links, or mutation responses.
- Sessions are revocable and expired sessions are cleared safely.
- All new UI strings are translated.
- Full `pytest` suite passes.
