# src/lib — infrastructure adapters

Thin wrappers around external services and cross-cutting concerns. No business logic.

```
auth.ts       Session handling and the identity adapter — see below
env.ts        Parsed, validated environment variables
email.ts      Transactional email (result release, booking confirmation)
blob.ts       Vercel Blob client
redis.ts      Upstash client — rate limiting and cache only, never job queues
```

## `auth.ts` is an adapter, deliberately

Integration with the main TestMu AI login is **deferred until the build is complete**
([`docs/auth.md`](../../docs/auth.md)). Everything else must be buildable in the meantime.

So: the rest of the app asks this module who the current user is and never knows how identity
arrived. Behind it sits a dev stub today and the real handoff later. Swapping them must be a
one-file change.

If auth assumptions leak into route handlers and components over months of building, late
integration becomes a refactor instead of a config change. This is the most important boundary
in the repo after `core/`.

`users.external_id` is an **opaque string** — never parsed, never assumed numeric, never assumed
to be an email.

## `env.ts`

Parse `process.env` through a Zod schema at startup so a missing variable fails fast and loudly
rather than surfacing as a null deep in a request. Every variable in `.env.example` belongs here.
