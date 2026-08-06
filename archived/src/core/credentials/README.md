# core/credentials

Issuance, verification, and revocation of earned credentials.

## The credential is a web page

`/verify/[credentialId]` is the canonical credential — not a PDF. It is revocable, updatable, and
shareable. Anything downloadable points back to it.

A PDF download is optional and low priority. If it happens, **generate it on demand** rather than
storing one: no Blob storage, no async job, and nothing to regenerate when a template or a name
changes. Use `pdf-lib` / `@react-pdf/renderer`, not headless Chrome.

## Issuance

- Issued on **result release**, only for a passing attempt. Never on submit.
- References the attempt and the frozen exam version, so the credential can always state exactly
  what was passed.
- **Idempotent** — re-running issuance for an attempt must not mint a second credential.
- Credential IDs must be **unguessable**. Never sequential integers; someone will enumerate them.

## Revocation and expiry

- Revocation is an explicit, audited admin action with a reason.
- A revoked or expired credential must render **unmistakably** as such on the public page. A
  revoked credential displaying as valid is the worst defect this product can produce — treat it
  with the same seriousness as a leaked answer key.
- Expiry runs via `/api/cron/expire-credentials`. Expired is a distinct state from revoked.

## Privacy

The verification page is public and indexable. It shows the holder's name, the certification, the
exam version, issue and expiry dates — and nothing else. Never the email, score, attempt history,
or answer breakdown.
