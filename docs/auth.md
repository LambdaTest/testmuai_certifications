# Authentication

**This app has no login screen and never handles a password.** Identity comes from the existing
TestMu AI login. Do not add a sign-in, sign-up, or forgot-password page to this repo.

## The flow

```
1. Candidate hits  /book                          (unauthenticated)
2. We redirect to  <MAIN_SITE_LOGIN>?redirect_uri=<our callback>&state=<signed return path>
3. Candidate signs in on the company's existing login screen
4. Main site redirects to  /api/auth/callback?code=<short-lived>&state=<...>
5. We exchange the code server-to-server for the user's identity
6. We upsert a local user row, mint OUR session cookie
7. We redirect to the original destination — /book
```

Step 7 matters: land the candidate where they were going, not on the dashboard. The intended
path travels in `state`, and `state` must be signed or server-stored — never a raw URL from the
query string, or it becomes an open redirect.

**The chosen certification is not part of this exchange.** The main site's redirect may carry an
exam identifier today; we ignore it. Candidates choose their exam from a selector on `/book`, so
identity and exam choice stay separate concerns. Do not read a certification from the auth
response, and do not let one appear in a session claim.

**Authentication is the only integration between the two systems.** There is no entitlement sync,
registration webhook, or catalog API — booking in this app *is* enrolment. If a future change
requires reading registrations from the main site, that is a new integration to spec, not an
extension of this one.

## What we need from the main site team

A tight, standard ask. If their login already speaks OAuth 2.0 / OIDC, this reduces to "issue us
a client ID and secret."

1. A login URL that accepts a **`redirect_uri`** and honours it after successful sign-in
2. Our callback URL **allowlisted** (production + preview deployments + localhost for dev)
3. On success, redirect back with a **short-lived, single-use `code`**
4. A **server-to-server exchange endpoint**: we POST `code` + client secret, they return the
   user's **stable ID**, email, and name

### Why a code exchange rather than a token in the URL

A JWT in the redirect URL leaks into browser history, `Referer` headers, and any access log
between here and the user. A code that is single-use, short-lived, and only redeemable with our
client secret does not — the identity payload never touches the browser. This is what OAuth does
and it costs the main site one extra endpoint.

If they genuinely cannot expose an exchange endpoint, a signed JWT in the redirect is an
acceptable fallback: TTL under 120 seconds, single-use, audience-scoped to this app, verified
against their public key. Note the trade-off explicitly if we go that way.

## Rules for this app

- **Key users on the main site's stable user ID.** `users.external_id` is unique; email is a
  mutable attribute, never an identity. People change email addresses, and a credential attached
  to the wrong person is not recoverable.
- **Roles are local.** Admin and grader permissions live in our database. The incoming token or
  identity payload must not be able to grant admin here — otherwise the main site's user table
  becomes a privilege-escalation path into the exam engine and the question bank.
- **We own our session.** An exam in progress must not end because the main site's session
  expired. Our session cookie has its own TTL.
- **Logout** clears our session and redirects to the main site's logout. Main-site logout does
  *not* propagate here automatically — accepted trade-off, keep our session TTL modest.
- **Never store a password, password hash, or reset token in this database.**

## Routes

| Route | Purpose |
|---|---|
| `GET /api/auth/login` | Builds the redirect to the main site login, signs `state` with the return path |
| `GET /api/auth/callback` | Verifies `state`, exchanges `code`, upserts the user, mints our session |
| `POST /api/auth/logout` | Clears our session, redirects to main-site logout |

Guarding happens in each route group's `layout.tsx` (see `docs/routes.md`), with middleware
doing a coarse cookie check first so unauthenticated requests never reach the database.

## Integration is deferred — build against a stub

**Decision:** we build the whole product first and integrate with the main site's login at the
end. Nothing in this app should wait on that.

This is workable, but auth is the one piece that cannot be exercised until they wire up, so
surprises surface late. Three rules keep that cheap:

1. **All auth behind one adapter** — `src/lib/auth.ts`. Route handlers and components ask that
   module who the user is; they never know how identity arrived. Swapping the stub for the real
   handoff is then one file, not a refactor. Auth assumptions leaking across the codebase during
   a months-long build is the expensive failure here.
2. **`users.external_id` is an opaque string.** Never parse it, never assume numeric, never assume
   it is an email. We do not yet know its shape, and a team that assumed integers for six weeks
   is a costly correction.
3. **`certifications.external_ref` is nullable and unused for now** — see
   `src/core/certifications/README.md`. It absorbs whatever identifier they eventually send.

**Get the integration spec early even though the implementation lands late.** Asking internal
teams or Eklavya for documentation is not a change request and costs the main-site team nothing.
It is the difference between building against a known contract and discovering at the end that
their handoff works nothing like we assumed.

## Local development

Developers cannot reach the company login from `localhost`, and a shared-domain cookie would not
work there either. Ship a **dev-only stub**: an endpoint behind `NODE_ENV !== 'production'` that
mints a session for a fixture user, so the whole team can work offline and CI can run end-to-end
tests. Guard it so it can never be enabled in a deployed environment.

## Open

- Confirm with the main site team: does their login already support OAuth 2.0 / OIDC, or does
  this need building? That determines whether this is a configuration task or an integration project.
- Will this app run on `certifications.testmuai.com` or a separate domain? A shared parent domain
  makes a session cookie possible as a simpler alternative — but it breaks local development and
  couples us to their session format, so the handoff above is still the recommendation.
