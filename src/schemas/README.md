# src/schemas — shared Zod contracts

Validation schemas shared between server and client. This is the payoff of TypeScript end to end:
one definition, checked in both places, with types derived rather than hand-written.

## Rules

- **Every external input is parsed here at the boundary** — request bodies, query params, form
  data, and anything arriving from the main site.
- **Parse, don't validate.** The schema's output type is what flows inward, so downstream code
  cannot receive an unvalidated shape. Never `as` a type past a boundary.
- Derive TypeScript types from schemas (`z.infer`), never maintain both by hand.

## Answer keys do not belong in candidate-facing schemas

Question schemas come in pairs — the candidate-facing shape has no `answer_key` field at all, so
including one is a type error rather than a leak. Make the wrong shape unrepresentable.

## Expected files

```
question.ts       Per-type payload schemas, discriminated on `type`
attempt.ts        Start, autosave response, submit
booking.ts        Slot selection, booking creation
certification.ts  Certification and exam version authoring
credential.ts     Issuance, verification response
common.ts         Pagination, ids, timestamps
```
