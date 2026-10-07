# Architecture

A short map of the codebase. For setup, see [README.md](README.md).

## Overview

CodeSpace is a React single-page app (SPA) and a FastAPI API, backed by PostgreSQL.

Both are served from **one origin**: the SPA at `/` and the API at `/api`. Locally, Vite proxies `/api` to the API.

```text
Browser ──► /      React SPA       (frontend/)
        └─► /api   FastAPI API     (backend/)  ──►  PostgreSQL
```

## Code map

### `frontend/src/`

- `router.ts`: all pages and which ones need a signed-in user.
- `routes/`: one file per page.
- `lib/api.ts`: every API call goes through `apiFetch()`.
- `components/`: shared UI. `components/ui/` is shadcn/ui.

### `backend/app/`

- `main.py`: builds the app and its middleware.
- `lifespan.py`: shared objects created at startup (database, HTTP client, email sender, OAuth providers).
- `api/`: the `/api` router, the CSRF check and the error format.
- `core/`: settings, email sending and request IDs.
- `models/`: the SQLAlchemy base class and mixins.
- `modules/<name>/`: one folder per feature, e.g. `auth` and `users`.

A module uses these layers, split into more files where it helps (e.g. `auth/password_router.py`):

| File | Job |
| --- | --- |
| `router.py` | HTTP only: parse the request, call a service, shape the response. |
| `service.py` | The rules and their queries: plain functions that take the database session. |
| `models.py` | Tables. |

Database migrations are in `backend/migrations/` (Alembic).

## Rules that always hold

- **One origin.** The API sends no CORS headers.
- **Every state-changing `/api` request passes the CSRF check.** The browser's `Sec-Fetch-Site` (or `Origin`) must name this origin.
- **API errors the SPA acts on are `{"detail": {"code", "message"}}`.** Build them with `api_error()`.

## Cross-cutting concerns

### Authentication

Users sign in with email and password, or with Google, Microsoft or GitHub. Sessions are server-side, in an `HttpOnly` cookie. Changing sign-in methods needs a fresh confirmation: the password, or an emailed link.

The code is in `backend/app/modules/auth/`. Full details are in [docs/auth.md](docs/auth.md).

### Request IDs

Every response has an `X-Request-ID` header. Logs, including the auth audit log, carry the same ID.

### Email

Production sends email with Resend. Other environments log it instead.
