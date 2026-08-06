# TestMu AI Certifications

In-house platform for delivering TestMu AI professional certifications — slot booking, exam
delivery, grading, and credential issuance. Replaces our current external vendor.

> **Status: skeleton.** Directory structure and specifications are in place; the application is
> not yet scaffolded and there is no implementation code. Every area has a `README.md` describing
> what belongs there. Pick up the area you own, read its README, and start adding files.

## Start here

**[`docs/master-spec.md`](docs/master-spec.md)** — purpose, scope, technology rationale,
architecture rules, open decisions, and an index of every module linking to its own spec.
A shareable Word version is at [`docs/master-spec.docx`](docs/master-spec.docx).

| Document | What it covers |
|---|---|
| [`docs/master-spec.md`](docs/master-spec.md) | The top-level specification and module index |
| [`docs/routes.md`](docs/routes.md) | Page inventory, auth guards, layouts |
| [`docs/auth.md`](docs/auth.md) | Identity handoff from the company login |
| [`docs/conventions.md`](docs/conventions.md) | Binding rules for the whole repo |

## Scope

**In:** everything from slot booking onwards — booking with capacity, timed exam delivery,
grading, result release, credentials and public verification, and the admin dashboards behind all
of it.

**Out:** the public catalog (already at `testmuai.com/certifications/`) and the login screen (the
company's existing one). This app has no sign-in UI and stores no passwords.

## Stack

| Layer | Choice |
|---|---|
| Language | TypeScript, end to end |
| Application | Next.js, App Router |
| Database | PostgreSQL (Neon) with Drizzle |
| Validation | Zod, shared between server and client |
| UI | Tailwind, shadcn/ui, TanStack Table, react-hook-form |
| Background work | Workflow DevKit + Vercel Cron |
| Hosting | Vercel Pro, Fluid Compute, Node.js 24 |

Rationale for each choice is in the master spec.

## Two rules to know before writing anything

1. **No long-running process exists.** We run on serverless functions. Anything that outlives a
   request belongs in `src/workflows/` or a cron route — never an in-process queue, worker, timer,
   or module-level cache. BullMQ and similar do not work here.
2. **Answer keys never reach the client.** Candidate-facing and grading-facing read models are
   separate types so the mistake is a compile error, not a leak. See
   [`docs/conventions.md`](docs/conventions.md).

## Layout

```
docs/          Specifications — read before building
scripts/       build-spec.py regenerates the .docx from the markdown
src/
  app/         Routes only. Thin — no business logic.
    (candidate)/   booking, dashboard, account
    (exam)/        the exam player, deliberately without navigation
    admin/         admin dashboard
    verify/        public credential verification
    api/           route handlers
  core/        Business logic. Framework-agnostic. The heart of the app.
  db/          Drizzle schema and migrations
  schemas/     Shared Zod contracts
  lib/         Auth adapter, env, third-party clients
  components/  React components
  workflows/   Durable background processes
tests/         Test suites
```

**Dependencies point one way: `app/ → core/ → db/`.** `core/` must never import React, `next/*`,
or anything from `app/`. That keeps the grading engine testable without HTTP and leaves the door
open to extracting `core/` into its own service later.

## Getting started

The repo intentionally ships without pinned dependency versions. Whoever sets up the project first
runs the scaffolding and commits the lockfile:

```bash
pnpm dlx create-next-app@latest . --ts --tailwind --app --src-dir --import-alias "@/*"
pnpm add drizzle-orm zod @neondatabase/serverless
pnpm add -D drizzle-kit
pnpm add workflow @workflow/next @vercel/blob @upstash/redis
pnpm add -D @vercel/config
pnpm dlx shadcn@latest init
pnpm add @tanstack/react-table react-hook-form @hookform/resolvers
```

`create-next-app` will overwrite `README.md`, `tsconfig.json`, and `package.json` — restore them
with `git checkout --` afterwards and merge in only the new dependency entries.

Then `cp .env.example .env.local` and fill it in.

## Ownership

One owner per area; owners review PRs touching their area.

| Area | Owner | Status |
|---|---|---|
| Project scaffolding | _TBD_ | Not started |
| Database schema + migrations | _TBD_ | Not started |
| Slot calendar component | _Assigned_ | In progress |
| Booking page | _TBD_ | Not started |
| Exam player | _TBD_ | Not started |
| Grading engine | _TBD_ | Not started |
| Credentials + verification | _TBD_ | Not started |
| Admin dashboards | _TBD_ | Not started |
| Auth adapter | _TBD_ | Not started |

## Open decisions

Nine unresolved decisions are tracked in
[the master spec](docs/master-spec.md#8-open-decisions). The three worth resolving first, because
they shape the schema:

1. **Late start** — does a candidate joining late get the full duration, or only until the slot ends?
2. **Code-execution question types** — do candidates write and run code?
3. **Payment** — is there a paid step? Booking is enrolment, so it would happen here.
