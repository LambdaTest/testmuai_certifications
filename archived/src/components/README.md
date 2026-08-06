# src/components

React components. This is where most "we need to share this" instincts should land — sharing a
component is almost always right, sharing a route almost always isn't.

```
ui/          shadcn/ui primitives. Generated — avoid hand-editing.
```

Suggested grouping as it grows: `booking/`, `exam/`, `admin/`, `credentials/`. Split by feature
rather than by type (`forms/`, `tables/`) — feature grouping keeps related files together as the
admin surface expands.

## Rules

- Components render and handle interaction. Business rules live in `src/core`.
- Server Components by default; add `"use client"` only where interactivity requires it.
- Anything rendered inside `(exam)/` is a high-risk surface for answer-key leakage — question
  components must accept a candidate-facing type that has no key field at all. See
  [`docs/conventions.md`](../../docs/conventions.md#answer-key-safety).
- Admin tables use TanStack Table; forms use react-hook-form with the Zod schema from
  `src/schemas` as the resolver.
