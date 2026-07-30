# src/app — routes only

Next.js App Router. **Thin by design.**

A page or route handler may: read params, check auth, call into `src/core`, render or respond.
It may not: contain grading rules, scoring maths, eligibility logic, or raw SQL. Those live in
`src/core` so they stay testable and portable.

Full route inventory and the rules for adding routes: [`docs/routes.md`](../../docs/routes.md).

```
(candidate)/   booking + signed-in candidate portal
(exam)/        the exam player — no navigation chrome, by design
admin/         admin dashboard, role-gated
verify/        public credential verification — the canonical credential
api/           route handlers
```

**Catalog and exam selection are out of scope** — they already exist on the main TestMu AI
site. This app is entered by deep link into `/book/[certificationSlug]`. There is no
marketing group here.

`layout.tsx` here is the root layout: html shell, fonts, global providers. Auth guards belong
in each **group's** layout, not here and not in individual pages.
