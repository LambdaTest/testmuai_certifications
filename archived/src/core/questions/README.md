# core/questions

The question bank. Questions are **reusable across exam versions** — authored once, selected into
many blueprints — so they are not owned by a version.

## Question types

Types differ enough that a single flat table would be mostly null columns. Model the common
fields as real columns (id, type, stem, tags, difficulty, status) and put type-specific structure
in a `JSONB` payload with `type` as the discriminator, validated by a Zod schema per type.

Known types: single-select, multi-select, true/false, short answer. **Code-execution is an open
decision** — if it lands, it needs a sandbox and a fundamentally different grading path, so keep
the payload shape open enough to accept it.

## Answer keys

`answer_key` lives on the question record and **must never reach the client**. Provide two
distinct read paths with distinct return types:

- `getQuestionForCandidate()` — stem, options, media. No key. Ever.
- `getQuestionForGrading()` — includes the key. Server-only callers.

Do not rely on remembering to strip a field. Make the wrong shape unrepresentable.

## Authoring rules worth enforcing

- A question cannot be published without a valid answer key for its type.
- A question used by a **published** exam version cannot be edited — clone it instead. Editing it
  would silently change what past candidates were scored against.
- Deleting is soft. Questions referenced by historical attempts must remain readable forever.
- Tags and difficulty are what make the bank usable at scale. Treat them as required, not optional.
