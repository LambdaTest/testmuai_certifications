# verify — public credential verification

**Auth:** none. This must work for an anonymous visitor with no account.
**Layout:** minimal, public, indexable.

`/verify/[credentialId]` is **the canonical credential** — not a PDF. It is revocable,
updatable, and shareable. Anything printed or exported points back here.

Requirements:

- Renders clearly for someone who has never heard of us — who earned it, which certification,
  which exam version, when issued, when it expires.
- **Revoked and expired states must be unmistakable.** A revoked credential showing as valid
  is the worst bug this product can have.
- Open Graph / Twitter card tags so it previews properly when shared to LinkedIn.
- Never expose the candidate's email, attempt history, or score breakdown. Public means public.
- Credential IDs must be unguessable — do not use sequential integers.
