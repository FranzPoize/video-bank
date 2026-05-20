---
date: 2026-05-20
topic: "User Account System"
status: draft
---

## Problem Statement

Video Bank currently treats videos, matches, and tags as application-wide resources. There is no concept of account ownership, authenticated users, or per-user permissions. The application needs a user and account system so each account owns its own videos, matches, and tags, while users can be granted specific rights inside one or more accounts.

The system must support direct signup and account invitations. A user who signs up from the public signup form receives a new account and becomes that account's administrator. An account administrator can invite other users, assign rights, and manage account membership. Email verification is required during signup so accounts are not created for unverified addresses.

## Constraints

- **Keep the application simple and testable** — avoid unnecessary inversion of control and keep business rules in explicit service functions.
- **Existing stack alignment** — preserve the FastAPI, Jinja2, HTMX, vanilla JavaScript, SQLite, and raw SQL architecture already used by the application.
- **No heavy identity platform by default** — use application-owned authentication unless a later implementation decision explicitly chooses an external provider.
- **Account isolation** — videos, matches, and tags must belong to an account, and every account-scoped operation must verify the current user's membership and rights.
- **Incremental migration** — existing data needs a safe default-account migration path so current installations remain usable after the account model is introduced.
- **Email verification required** — new email identities cannot be treated as active until verification succeeds.
- **Invitation flow required** — admins need to invite users into an existing account and preselect rights before or during acceptance.
- **Internationalization** — all new UI strings should follow the existing translation approach.
- **Session security** — authenticated sessions need secure cookies, logout support, and protection against stale or revoked memberships.

## Approach

Use an application-owned authentication and authorization layer built around four core concepts: users, accounts, memberships, and invitations.

Users represent login identities and store email, password credentials, and verification state. Accounts own all business data. Memberships connect users to accounts and carry permission flags. Invitations allow an account administrator to invite an email address into an account with a chosen set of rights.

Authorization remains explicit and resource-oriented. Each protected route resolves the current user, selects an active account, loads the user's membership for that account, and checks the required permission before calling the underlying service. Account-scoped services receive an account identifier and only read or mutate rows belonging to that account.

Permissions are modeled as named capabilities rather than a single role-only switch. A default administrator membership receives all capabilities, while invited users can receive rights such as managing videos, matches, tags, account settings, and user rights. Roles may be used in the UI as presets, but the persisted authorization decision should remain capability-based for flexibility.

## Architecture

The system adds an authentication boundary in front of existing route handlers and an account boundary inside existing services.

- The request middleware or route dependencies resolve the authenticated session into a current user.
- Account selection determines which account the request is acting on.
- Authorization helpers check the user's membership capabilities for the selected account.
- Account-aware service functions operate on videos, matches, tags, and settings using the selected account identifier.
- Authentication services handle signup, login, logout, email verification, password hashing, and session lifecycle.
- Invitation services handle invite creation, acceptance, expiration, revocation, and membership creation.

Existing domain areas remain recognizable. Videos, matches, tags, clips, and related UI continue to use their current routes and templates, but those screens become account-scoped and hidden behind authentication where appropriate.

## Components

### Authentication Service

Responsible for user signup, login, logout, password hashing, credential validation, email verification token creation, email verification completion, and session creation. It owns user identity rules such as unique email addresses and verified-email requirements.

### Account Service

Responsible for creating accounts, updating account metadata, listing accounts available to the current user, and choosing the active account context. Direct signup uses this service to create the user's initial account and administrator membership in one transaction.

### Membership and Permission Service

Responsible for checking account membership, assigning capabilities, changing user rights, removing users from accounts, and ensuring at least one account administrator remains. It provides a single place for route handlers and domain services to ask whether a user may perform an action.

### Invitation Service

Responsible for creating invitations, storing the invited email address, selected capabilities, expiration state, acceptance state, and inviter metadata. Accepting an invitation either attaches an existing verified user to the account or guides a new user through signup and email verification before membership activation.

### Account-Scoped Domain Services

Existing video, match, tag, clip, and settings services become account-aware. They accept account context and filter all account-owned reads and writes by account. Create operations attach new rows to the active account.

### Route and Template Layer

New pages include signup, login, logout, email verification result, invitation acceptance, account switcher, account settings, member list, invite form, and member-rights editor. Existing pages show only data for the active account and surface controls based on the current user's permissions.

### Email Delivery Adapter

The design requires an email-sending boundary for verification and invitation messages. The implementation can start with a simple SMTP or console-backed adapter, provided the service interface keeps tests deterministic and avoids sending real email during test runs.

## Data Flow

### Direct Signup

A visitor submits email and password through the signup form. The authentication service creates an unverified user and a verification token. The system sends a verification email. After the user verifies the email address, the account service creates the initial account and administrator membership, then the user can sign in and access account-owned resources.

### Login and Account Selection

A verified user submits credentials. The authentication service validates the password and creates a session. The application loads the user's memberships and selects a default active account, usually the most recent account or the only available account. If the user belongs to multiple accounts, the account switcher lets them change the active account context.

### Inviting a User

An account administrator opens the member management screen, enters an email address, and selects capabilities. The permission service verifies that the inviter may manage user rights. The invitation service creates an invitation for the account and sends an invitation email. The invitation remains pending until accepted, revoked, or expired.

### Accepting an Invitation

The invited user opens the invitation link. If they already have a verified account with the invited email, accepting the invitation creates or updates membership for the target account. If they do not have a user account, they complete signup and email verification first. After acceptance, the user can access the account with the invited rights.

### Accessing Account-Owned Data

For each protected request, the application resolves the current user and active account, validates membership, checks the capability required for the requested action, and calls the relevant account-scoped service. The service returns only rows owned by the active account.

### Changing Rights

An administrator edits a member's capabilities. The permission service validates that the acting user may manage rights and that the change does not remove the last administrator from the account. Updated rights take effect on the next request and should invalidate or refresh any cached permission state.

## Error Handling

| Scenario | Response |
|----------|----------|
| Signup with existing email | Show a generic account-related message without revealing more than necessary. |
| Login with invalid credentials | Return the same error for unknown email and wrong password. |
| Unverified email attempts login | Prompt the user to verify email and offer to resend verification. |
| Expired or invalid verification token | Show a safe failure page and allow requesting a new token. |
| Expired, revoked, or already-used invitation | Show an invitation error page with next steps. |
| User lacks account membership | Return forbidden or redirect to account selection if another account is available. |
| User lacks required capability | Return forbidden and do not perform the requested mutation. |
| Account-scoped resource not found | Return not found rather than exposing whether the resource exists in another account. |
| Attempt to remove last administrator | Reject the change with an explanatory validation error. |
| Email delivery failure | Keep the user-facing state consistent, log the failure, and allow resend. |
| Session expired or revoked | Clear the session and redirect to login. |

## Testing Strategy

- **Authentication tests** — signup, duplicate email behavior, password validation, login, logout, session expiration, and unverified-email restrictions.
- **Email verification tests** — token creation, successful verification, expired token handling, invalid token handling, and resend behavior.
- **Account creation tests** — direct signup creates a user-owned account and administrator membership after verification.
- **Membership tests** — user-to-account links, capability assignment, capability updates, member removal, and last-admin protection.
- **Invitation tests** — invite creation, invitation acceptance by existing users, invitation acceptance by new users, revoked invitation handling, expired invitation handling, and rights application.
- **Authorization tests** — each protected action checks the required capability and rejects users without access.
- **Account isolation tests** — videos, matches, tags, and settings from one account never appear in another account's reads or writes.
- **Migration tests** — existing data is assigned to a default account and remains accessible to the migrated administrator.
- **Route and template tests** — signup, login, verification, invitation, account switching, member management, and permission-gated controls render correctly.
- **Security regression tests** — invalid sessions, stale memberships, cross-account identifiers, and forged account-selection values are rejected.

## Open Questions

- Which email delivery option should be used first: SMTP configuration, a transactional email provider, or a console-only development adapter with production selection later?
- Should direct signup create the account only after email verification, or create a disabled account immediately and activate it after verification?
- What are the exact capability names and default presets for video, match, tag, account settings, and user-rights management?
- Should users be allowed to belong to multiple accounts from the first implementation, or should the UI hide account switching until it is needed?
- Should password reset be included in the first implementation checkpoint or handled as a follow-up feature?
- How should existing single-user installations identify the initial administrator during migration?
