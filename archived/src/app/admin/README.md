# admin — admin dashboard

**Auth:** session + admin role. Enforce in `layout.tsx` — pages inherit it.
**Layout:** admin sidebar.

`/admin` is a real URL segment (not a route group) because we want it visible in the URL.

Scope: managing the product and other people. Certifications, exam versions, the question bank,
grading, credentials, candidates, settings.

Full page list: [`docs/routes.md`](../../../docs/routes.md#admin--the-product-and-other-people).

## Notes for whoever builds here

- `/admin/attempts/[attemptId]` is the **dispute-resolution screen**. It must show the full
  audit trail — what was served, what was answered, when, and how it was scored. Build it
  assuming someone will contest a result.
- Publishing an exam version **freezes it**. Edits create a new version; they never mutate a
  published one. Past attempts must remain explainable years later.
- Bulk operations (question import, credential revocation) are the ones that cause damage.
  Confirm destructive actions and write to the audit log.
