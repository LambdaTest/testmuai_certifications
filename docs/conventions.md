# Conventions

Rules that apply everywhere in this repo. Deviating from these is a review-blocking issue.

## Where logic goes

Four layers. The right one depends on **what could bypass it**:

| Layer | Catches | Example |
|---|---|---|
| **Database constraint** | Everything — shell, admin, `bulk_create`, raw SQL | `exam_duration_matches_type`, `one_open_booking_per_exam` |
| **Model `clean()` / `save()`** | Anything through the ORM, admin included | `Exam.save()` filling `duration_minutes` |
| **Form `clean()`** | Form submissions, with a readable error | lead time, booking horizon, clash detection |
| **View** | This request only | ownership checks, redirects, context |

> The further down you push a rule, the harder it is to bypass — and the worse the error message
> gets. Put it as low as it needs to be for safety, then add a layer above it for a decent message.

The duration rule sits at three levels deliberately: `save()` fills it in, `clean()` gives a
readable error, and the `CheckConstraint` catches what skips both — `bulk_create` bypasses
`save()` entirely.

**Forms validate; views orchestrate.** The test: *could this rule be checked without an HTTP
request?* If yes it belongs in the form. If a form rule needs something request-derived, pass it
in rather than moving the rule to the view — `BookingForm(request.POST, candidate=request.user)`.

`book()` and `reschedule()` share `ScheduleForm`, so the scheduling rules exist once. Two copies
would eventually let one route accept a slot the other rejects.

## Timezones

**Every conversion between a candidate's wall-clock choice and the stored UTC instant lives in
`apps/exam/timezones.py`.** Nowhere else.

- Store `timestamptz`, always UTC.
- Keep the IANA zone the candidate booked in alongside it — that's what reminders display and
  what you reason about when someone disputes the time.
- Display in that zone, **always with the offset labelled**.

**A pre-converted datetime does not survive a template filter.** With `USE_TZ = True`, Django's
`date` filter converts any aware datetime to `settings.TIME_ZONE` — which is UTC — before
formatting. So this silently renders UTC:

```django
{{ booking.local_scheduled_at|date:"g:i A" }}   {# wrong #}
```

Render the raw field inside an explicit block instead:

```django
{% timezone booking.booked_timezone %}
  {{ booking.scheduled_at|date:"g:i A" }}
{% endtimezone %}
```

Nothing errors — you just get the wrong time, which for this product means someone misses their
exam.

## Answer-key safety

**Answer keys must never reach the candidate.** Not in a context variable, a template, an API
response, or a rendered payload.

- Keep the key on the question record and **never select it** in a query feeding a
  candidate-facing surface.
- Use separate read paths with separate return shapes — one for candidates, one for grading. Do
  not rely on remembering to strip a field.
- Grading happens server-side only. There is no scenario where the client scores anything.
- The exam player is the highest-risk surface. Review what it renders specifically.

A leaked answer key invalidates every credential issued from that question. It is the most
serious defect class in this codebase, and it needs a test rather than a review checklist.

## HTTP

- **Anything that mutates is a POST** with a CSRF token. A destructive GET can be triggered by
  browser prefetch, link previews and mail scanners.
- **Redirect after a successful POST.** A reload repeats the last request; if that was a POST, it
  submits again. This is why `book()` returns a 302 rather than rendering.
- **Mutating endpoints are idempotent** where possible — clients retry and users double-click.
  `cancel_booking` filters on `status=BOOKED` in the lookup, so a second POST 404s instead of
  doing anything.

## Database

- **Constraints belong in the database.** `UNIQUE`, `CHECK`, foreign keys — they catch what code
  review misses.
- Beware `NULL` in a unique constraint: two `NULL`s are never equal in Postgres, so
  `one_open_booking_per_exam` does nothing while `candidate` is null.
- Public identifiers — credential ids above all — must be **unguessable**. Never sequential.
- Migrations are forward-only. Never edit one that has been applied. Resetting the history is free
  now and impossible after launch.
- Soft-delete anything referenced by a historical attempt. Questions and exams must stay readable
  forever.

## Immutability where it matters

- A **published exam** is frozen once someone has attempted it. Edits create a new version.
- A **submitted attempt** is never mutated. Grading writes alongside it.
- The **audit log is append-only.**
- `credentials.holder_name` is a **snapshot at issuance** — it must not follow later changes to
  `display_name`, or a name change silently rewrites every credential someone holds.

A candidate disputing a result years later must be able to see exactly what was served, what they
answered, and how it was scored. Design for that conversation.

## Naming

- Python: `snake_case`. Templates and static files: `snake_case.html`, `kebab-case.css`.
- Database tables and columns: `snake_case`, tables plural — set `db_table` explicitly rather than
  accepting Django's `app_model` default.
- Booleans read as assertions: `is_published`, `has_expired`.
- Timestamps end in `_at`; **durations state their unit**: `duration_minutes`, never `duration`.

## Templates

- Extend `base.html`. Never duplicate the header, footer or theme tokens.
- Design tokens live in one place — the `@theme` block in `base.html`, mirrored in
  `static/css/input.css` for the production build. No one-off hex values.
- `{# … #}` comments a **single line only**. Multi-line needs `{% comment %}…{% endcomment %}`,
  or it renders as visible text on the page.
- Reverse URLs by name — `{% url 'exam:book' %}` — never hardcode a path.

## Git

- Branch from `main`: `feat/…`, `fix/…`, `chore/…`.
- Small commits with a message saying *why*, not just what.
- Before merge: `manage.py check`, `manage.py makemigrations --check --dry-run`, and the tests
  once they exist.
