# api/auth — identity handoff from the main TestMu AI login

**There is no login UI in this repo.** These routes only receive an already-authenticated user
from the company's existing login screen and turn that into a local session.

| Route | Purpose |
|---|---|
| `GET /login` | Redirect to the main site login with `redirect_uri` and a signed `state` carrying the return path |
| `GET /callback` | Verify `state`, exchange `code` server-side, upsert the user, mint our session |
| `POST /logout` | Clear our session, redirect to main-site logout |

Full contract, including what we need from the main site team: [`docs/auth.md`](../../../../docs/auth.md).

## Do not get these wrong

- **`state` must be signed or server-stored.** Redirecting to a raw URL from the query string is
  an open redirect.
- **Never trust roles from the incoming payload.** Admin permissions are looked up locally.
- **Key the user on `external_id`, not email.**
- The dev-only session stub must be unreachable when `NODE_ENV === 'production'`.
