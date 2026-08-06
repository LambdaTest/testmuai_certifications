# (exam) — the exam player

**Auth:** session required **and** the user must own this attempt. Check both in `layout.tsx`.
**Layout:** deliberately bare. No nav, no footer, no links out of the exam.

This is a separate group from `(candidate)` for one reason: it must not render navigation.
A nav bar mid-exam invites candidates to leave and muddies our "did they navigate away"
telemetry. Do not add global chrome here, and do not move these routes under `/dashboard`.

Pages: `/exam/[attemptId]/instructions` → `/exam/[attemptId]` → `/exam/[attemptId]/submitted`.

## Non-negotiables

- **The timer is server-authoritative.** `started_at` / `expires_at` live in Postgres. The
  countdown shown to the candidate is display only. Every response write and the final submit
  revalidate the deadline server-side — a tampered client clock must not buy extra time.
- **Answer keys never reach the client.** The payload sent to the player contains questions and
  options only. See `docs/conventions.md`.
- **Autosave responses.** A closed tab or dropped connection must not lose work.
- **No module-level state.** There is no long-lived process on Vercel; attempt state lives in
  Postgres, not in memory.
