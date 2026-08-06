# src/app/api — route handlers

Thin. Every handler follows the same four steps:

1. Parse and validate input with a Zod schema from `src/schemas`
2. Authorize (session, role, resource ownership)
3. Call a function in `src/core`
4. Shape the response

Business logic in a route handler is a review-blocking issue — it belongs in `src/core` where
it can be unit tested without HTTP.

## Planned surface

| Route | Purpose |
|---|---|
| `POST /api/attempts` | Start an attempt. Validates eligibility, freezes the served question set. |
| `GET /api/attempts/[attemptId]` | Current attempt state (no answer keys) |
| `PATCH /api/attempts/[attemptId]/responses` | Autosave a response |
| `POST /api/attempts/[attemptId]/submit` | Submit. Idempotent — a double-click must not double-submit. |
| `GET /api/attempts/[attemptId]/result` | Score report, once grading is complete |
| `/api/admin/*` | Admin operations, role-gated |
| `/api/cron/*` | Vercel Cron targets — see below |

## Cron routes

Declared in `vercel.ts`. Vercel does **not** authenticate them for us: every `/api/cron/*`
handler must verify the `CRON_SECRET` header itself and return 401 otherwise. Without that
check they are public endpoints.

Current: `/api/cron/expire-attempts` (every 5 min), `/api/cron/expire-credentials` (daily).

## Reminders for this platform

- No long-running work. Anything past a request goes to `src/workflows/` or a cron route.
- No module-level caches or in-memory state — function instances are reused unpredictably.
- Submit and issuance endpoints must be **idempotent**; clients retry.
