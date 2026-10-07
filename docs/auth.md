# Authentication

How people sign in to CodeSpace, and how the app keeps that safe.

For the big picture of the whole app, see [ARCHITECTURE.md](../ARCHITECTURE.md).

## Sign-in methods

A user can sign in with any of these:

- **Email and password**
- **Google**, **Microsoft** or **GitHub**

One user can have several methods. The app never removes the last one.

## Data

| Table | Holds |
| --- | --- |
| `users` | The person: name, avatar, active flag. |
| `user_emails` | A user's addresses. A verified address belongs to one user only. |
| `password_credentials` | The Argon2id hash, if the user has a password. |
| `oauth_accounts` | Linked provider accounts, at most one per provider. |
| `user_sessions` | Signed-in browsers. Stores a hash of the token, never the token. |
| `email_tokens` | Emailed links. Stores a hash of the secret, never the secret. |
| `rate_limit_counters` | Attempt counts for rate limiting. |

Emails are compared by `normalize_email()`, which is stored as `normalized_email`.

Provider accounts are matched by the provider's permanent user ID, never by email:

- Google: `sub`
- Microsoft: `<oid>.<tid>`
- GitHub: numeric `id`

## Sessions

- **Cookie:** `__Host-Http-session`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.
- **Expiry:** 14 days at most, or 30 minutes without a request.
- **New token on every sign-in.** Any old session in that browser is revoked first, which stops session fixation.
- **Sign out:** this browser (`/logout`) or every browser (`/logout-all`).

### Recent authentication

Adding or removing a sign-in method needs proof that the person is present now, not just a session.

A session counts as recent for **10 minutes** after one of these:

- Signing in with a password, or finishing sign-up.
- Entering the password again.
- Opening an emailed link, **in the same browser** that asked for it.

A provider sign-in is **not** recent: the provider may have answered from its own saved session, and providers can't be relied on to ask again ([Google doesn't support it](https://developers.google.com/identity/siwg/security-bundle)).

## Flows

### Sign up (email first)

1. The user enters an email. The API emails a link (valid 1 hour).
2. If the address already has an account, the API emails "you already have an account" instead. The response is the same either way, so the form doesn't reveal who has an account.
3. The user opens the link, then picks a name and password. The account is created and signed in.

### Sign in with a password

- One error for every failure: "Incorrect email or password."
- Unknown emails take as long to check as wrong passwords, so timing doesn't reveal accounts.
- Old hashes are upgraded to the current Argon2 settings on sign-in.

### Sign in with a provider

1. The browser goes to the provider (OAuth with PKCE). The flow's state lives in a signed cookie, `__Host-Http-oauth`, for 10 minutes.
2. On return, the API checks the response and finds the user by provider ID.
3. If the provider is new to the app:
   - The provider's email is **already verified by another user**: sign-in is refused with `account_exists`. The user signs in the usual way, then links the provider in settings. Accounts are never joined by email alone.
   - Otherwise a new user is created. A provider-verified email is saved as their primary email.

### Link and unlink a provider

- Both need recent authentication.
- Linking also needs the same user to still be signed in when the provider returns.
- Unlinking is refused if it would leave no way to sign in. A row lock stops two removals racing.

### Passwords

| Action | How | After |
| --- | --- | --- |
| Reset | Emailed link (30 min), only to a verified address with a password | Signs out every browser. The user signs in again. |
| Add | Emailed link (30 min) to the primary email. Needs recent auth. | |
| Change | Current password plus a new one | Signs out other browsers. Renews this one. |
| Remove | Needs recent auth | Refused if it's the last sign-in method. |

**Password rules** (NIST SP 800-63B):

- 15 to 256 characters, with no other composition rules.
- Normalized to Unicode NFC first.
- Checked against Have I Been Pwned. Only the first 5 characters of the SHA-1 hash leave the server. If the check is down, the password is allowed.

## Emailed links

- Each link holds a random 256-bit secret. Only its SHA-256 hash is stored.
- Single use. Used up in one database update, so two clicks can't both succeed.
- The secret is in the URL **fragment** (`#token=...`). Browsers don't send fragments, so it stays out of server logs. The page reads it and posts it to the API.
- Asking for a new reset, setup or "confirm it's you" link cancels the account's earlier one of that kind.
- Every send has an idempotency key, so a retry doesn't send twice.

| Link | Valid for |
| --- | --- |
| Sign up | 1 hour |
| Confirm it's you | 15 minutes |
| Reset password | 30 minutes |
| Add password | 30 minutes |

## Protections

### CSRF

The SPA and API share one origin, and the API sends no CORS headers.

Every `POST`, `PUT`, `PATCH` or `DELETE` under `/api` must have `Sec-Fetch-Site: same-origin`, or, if the browser doesn't send it, an `Origin` equal to `APP_URL`. Browsers set both headers themselves, so the SPA adds nothing.

This is [Fetch Metadata with the `Origin` fallback](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#fetch-metadata-headers) that OWASP requires. It refuses cross-site pages and same-site siblings alike. `SameSite=Lax` cookies are a second layer.

### Rate limits

Fixed windows, counted in PostgreSQL and shared by every worker. Too many attempts get `429` with `Retry-After`. Nothing is locked: the window just passes.

Email buckets are keyed by an HMAC of the address, so the table stores no addresses.

| Action | Per email | Per IP | Per user |
| --- | --- | --- | --- |
| Sign up | 3 / hour | 20 / hour | |
| Sign in | 10 / 15 min | 50 / 15 min | |
| Forgot password | 3 / hour | 20 / hour | |
| Password check (reauth, change) | | | 10 / 15 min |
| "Confirm it's you" email | | | 5 / hour |
| Add-password email | | | 5 / hour |

IPv6 clients are grouped by /64.

### Provider checks

- PKCE (`S256`) for every provider.
- ID tokens must list this app in `aud` and come from the expected issuer. Microsoft's issuer is checked per tenant.
- The `iss` response parameter is checked when the provider supports it (RFC 9207).
- The account picker is always shown, so users can switch provider accounts.

### Audit log

Security events go to the `app.auth.audit` logger with the request ID, e.g. `auth.login.succeeded` or `auth.password.reset`. Secrets are never logged.

## Code map

Backend, `backend/app/`:

| Path | What |
| --- | --- |
| `modules/auth/router.py` | Sessions, `/me`, sign-in methods, provider sign-in and linking |
| `modules/auth/password_router.py` | Sign-up, password sign-in, "Confirm it's you", password management |
| `modules/auth/service.py` | The rules for signing in and for adding or removing sign-in methods |
| `modules/auth/session.py` | Sessions and the session cookie |
| `modules/auth/tokens.py` | Secrets and emailed-link tokens |
| `modules/auth/passwords.py` | Hashing and password rules |
| `modules/auth/rate_limit.py` | Rate limiting |
| `modules/auth/providers/` | One adapter per provider |
| `modules/auth/dependencies.py` | `CurrentUser`, `RecentlyAuthenticatedSession` and other FastAPI dependencies |
| `modules/auth/emails.py` | The emails auth sends |
| `modules/users/emails.py` | `normalize_email()` |
| `modules/users/service.py` | Email address lookups |
| `api/csrf.py` | The CSRF check |

Frontend, `frontend/src/`:

| Path | What |
| --- | --- |
| `lib/api.ts` | API calls, `apiFetch()`, reading `#token=` from the URL |
| `lib/require-auth.ts` | Sends signed-out users to `/login` |
| `routes/` | Sign-in, sign-up, reset, settings and other pages |

## Setup

See [Same-origin deployment](../README.md#same-origin-deployment) in the README for:

- `APP_URL` and the provider redirect URIs
- proxy settings
- the Microsoft `xms_edov` claim, without which Microsoft emails count as unverified

Auth settings in `backend/.env`:

| Variable | For |
| --- | --- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Microsoft sign-in |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub sign-in |
| `OAUTH_SESSION_SECRET_KEY` | Signs the OAuth flow cookie |
| `RATE_LIMIT_SECRET_KEY` | HMAC key for email rate-limit buckets |
| `RESEND_API_KEY`, `EMAIL_FROM` | Sending email in production (other environments log it) |
