# src/workflows — durable background processes

Anything that must outlive a single request. Built with the Workflow DevKit
(`"use workflow"` / `"use step"`).

**There is no long-running process on Vercel.** No BullMQ, no in-process queue, no worker, no
`setInterval`. If work needs to survive a response, it belongs here or in a cron route.

## Why durable execution rather than fire-and-forget

Steps are retried individually and their results persisted. A failed email send does not re-run
grading; a redeploy mid-process does not lose the run. For a pipeline that ends in "tell someone
whether they passed", partial failure that silently drops the notification is the outcome to
design against.

## Expected workflows

```
grade-attempt.ts       On submit: auto-grade objective responses, route the rest to the
                       manual queue, mark graded. Does NOT notify — release is separate.
release-results.ts     On admin release for a slot: publish results, issue credentials for
                       passes, send result emails.
booking-confirm.ts     Booking confirmation and slot reminders (sleep-based).
```

## Rules

- Put logic in `"use step"` functions — they have full Node access. `"use workflow"` functions
  run sandboxed and should only orchestrate.
- Everything passed between steps must be serialisable. Pass IDs, not objects with methods.
- Steps must be **idempotent**; they can be retried.
- Use `FatalError` for permanent failures and `RetryableError` for transient ones, so a bad
  email address does not retry forever.

Scheduled work that is not a durable process belongs in `/api/cron/*`, declared in `vercel.ts`.
