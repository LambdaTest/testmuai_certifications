# Conventions

Rules that apply everywhere in this repo. Deviating from these is a review-blocking issue.

## The dependency rule

```
app/  →  core/  →  db/
```

Dependencies point one direction only.

- `core/` must **never** import from `app/`, and must never import React or `next/*`.
- `db/` knows nothing about `core/` or `app/`.
- `app/` is thin: parse input, authorize, call `core/`, shape the response.

This is what keeps the option open to lift `core/` into a standalone service later without a
rewrite. It also means the grading engine can be unit tested without booting Next.js — which
matters, because grading is the part that must be provably correct.

## Answer-key safety

**Answer keys must never reach the client.** Not in a prop, not in a payload, not in a server
component's serialized output, not in an API response, not in a source map.

- Keep the key on the question record (`answer_key`) and **never select it** in any query that
  feeds a candidate-facing surface.
- Use separate read models: `getQuestionForCandidate()` and `getQuestionForGrading()`. Do not
  rely on remembering to strip a field — return types should make the mistake impossible.
- Grading happens server-side only. There is no scenario where the client scores anything.
- Anything under `(exam)/` is the highest-risk surface. Review payloads there specifically.

A leaked answer key invalidates every credential issued from that question. Treat it as the
most serious defect class in this codebase.

## Platform constraints (Vercel)

- **No long-running processes.** Anything that outlives a request goes to `src/workflows/` or a
  cron route. No in-process queues, workers, or timers.
- **No module-level state.** Function instances are reused unpredictably; a module-scope cache,
  counter, or map will behave differently in production than locally.
- **Everything that mutates must be idempotent.** Clients retry; users double-click.

## Database

- Constraints belong in the database, not in application code. `UNIQUE`, `CHECK`, and foreign
  keys catch what code review misses.
- **Timestamps are `timestamptz`, always UTC.** Convert for display only. Exam slots and timers
  are the whole product — a timezone bug means someone misses their exam.
- Money, if it appears, is integer minor units. Never a float.
- Public-facing identifiers (credential IDs especially) must be **unguessable** — never
  sequential integers.
- Migrations are forward-only and reviewed. Never edit a migration that has been applied.

## Validation

Every external input is parsed with a Zod schema from `src/schemas` at the boundary — request
bodies, query params, and anything arriving from the main site. Schemas are shared between server
and client so the contract is checked in both places.

Parse, don't validate: the schema's output type is what flows inward, so downstream code cannot
receive an unvalidated shape.

## Immutability where it matters

- A **published exam version** is frozen. Edits create a new version.
- A **submitted attempt** is never mutated. Grading writes to separate columns and rows.
- The **audit log is append-only.**

A candidate disputing a result years later must be able to see exactly what was served, what they
answered, and how it was scored. Design for that conversation.

## Naming

- Files and directories: `kebab-case`. React components: `PascalCase.tsx`.
- Database tables and columns: `snake_case`, tables plural (`exam_slots`, `attempt_responses`).
- Booleans read as assertions: `is_published`, `has_expired`.
- Timestamps end in `_at`; durations state their unit: `duration_minutes`.

## Git

- Branch from `main`: `feat/…`, `fix/…`, `chore/…`.
- Small PRs. One reviewer minimum; area owners review their own area.
- CI must pass `pnpm typecheck`, `pnpm lint`, and `pnpm test` before merge.
