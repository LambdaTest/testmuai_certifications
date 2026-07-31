# src/core — business logic

The heart of the app. Framework-agnostic by rule: **no React, no `next/*` imports, no imports
from `src/app`.** Everything here must be unit testable without booting Next.js.

That rule exists for two reasons. The grading engine has to be provably correct, and proving it
is far easier without HTTP in the way. And keeping `core/` portable means it can be lifted into a
standalone service later without a rewrite — a real possibility once exam volume grows.

```
certifications/   Certification products and versioned exam blueprints
questions/        Question bank, question types, authoring rules
attempts/         Attempt lifecycle, timers, response capture
grading/          Scoring, pass/fail determination
credentials/      Issuance, verification, revocation
```

Slots and bookings currently live under `attempts/`. If booking logic grows past a couple of
files, split it into `core/booking/` rather than letting `attempts/` sprawl.

Full rules: [`docs/conventions.md`](../../docs/conventions.md).
