# Conventions

Rules that apply everywhere in this repo. Deviating from these is a review-blocking issue.

## Where logic goes

Four layers. The right one depends on **what could bypass it**:

| Layer | Catches | Example |
|---|---|---|
| **Database constraint** | Everything — shell, admin, `bulk_create`, raw SQL | `exam_duration_matches_type`, `one_open_booking_per_exam` |
| **Model `clean()` / `save()`** | Anything through the ORM, admin included | `Exam.save()` filling `duration_minutes` |
| **Form `clean()`** | Form submissions, with a readable error | lead time, booking horizon, clash detection |
| **Formset `clean()`** | Rules spanning several rows of the same form | exactly one correct answer option |
| **View** | This request only | ownership checks, redirects, context |

> The further down you push a rule, the harder it is to bypass — and the worse the error message
> gets. Put it as low as it needs to be for safety, then add a layer above it for a decent message.

The duration rule sits at three levels deliberately: `save()` fills it in, `clean()` gives a
readable error, and the `CheckConstraint` catches what skips both — `bulk_create` bypasses
`save()` entirely.

**A rule that spans rows belongs on the formset, not the form.** "An objective question needs at
least two options and exactly one correct" cannot be a field validator — one option knows nothing
about its siblings — and cannot be a `CheckConstraint`, because Postgres checks a row against
itself, not against a set. `BaseAnswerOptionFormSet.clean()` is the only place it can live.
Raising there produces a non-form error, rendered through `formset.non_form_errors`.

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

## File uploads

**A model-field validator does not run on `objects.create()`.** `Model.save()` never calls
`full_clean()`, so the `FileExtensionValidator` on `Image.image_file` fires only when a ModelForm
validates an `Image`. Any form that creates a media row itself must **re-declare** the validator
on its own field. This is not a Django quirk to work around — it is why `QuestionForm` carries the
extension list a second time.

**Django imposes no upload size limit.** `FILE_UPLOAD_MAX_MEMORY_SIZE` only decides between memory
and a temp file; `DATA_UPLOAD_MAX_MEMORY_SIZE` explicitly excludes file data. If a size limit
matters, it is a form validator and nothing else.

**`accept` on a file input is a hint to the file picker.** It filters what the dialog shows and is
ignored by any direct post. So is a byline stating a limit. Neither is a check.

**Files arrive in `request.FILES`, not `request.POST`** — a `FileInput` widget reads only from
`files`. A form constructed as `Form(request.POST)` drops every upload *silently*, because a
`required=False` file field cleans an absent value to `None` without complaint. Both dicts, always:
`Form(request.POST or None, request.FILES or None)`. The `<form>` needs
`enctype="multipart/form-data"` or the browser posts filenames instead of files, also silently.

**Uploads live under `MEDIA_ROOT`, never `STATIC_ROOT`.** Static files ship with the code; media
arrives at runtime and must survive a deploy. Local disk is development-only — an instance that
gets replaced loses every upload.

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
- Anything a past paper references must stay readable forever. Prefer `PROTECT` on the reference
  over remembering to soft-delete: `ExamSheetQuestion.question` is what stops a served question
  being deleted, and it holds against the shell and the admin, not just a view.

## Immutability where it matters

- **Questions are never edited.** The Question Bank has no edit page and will not get one. That is
  what lets `ExamSheetQuestion` reference a question by foreign key rather than snapshotting its
  text, and it replaces the earlier plan of versioning published exams — versioning was needed
  because questions were assumed editable.
- **A served question cannot be deleted.** `ExamSheetQuestion.question` is `PROTECT`, so the
  database refuses. Questions in circulation are withdrawn by setting `status` to `retired`, never
  removed. Questions never served stay freely deletable.
- A **submitted sheet** is never mutated. Grading writes alongside it, into `marks_awarded`.
- The **audit log is append-only.**
- `credentials.holder_name` is a **snapshot at issuance** — it must not follow later changes to
  `display_name`, or a name change silently rewrites every credential someone holds.

A candidate disputing a result years later must be able to see exactly what was served, what they
answered, and how it was scored. Design for that conversation.

## Naming

- Python: `snake_case`. Templates and static files: `snake_case.html`, `kebab-case.css`.
- Database tables and columns: `snake_case`, tables plural — set `db_table` explicitly rather than
  accepting Django's `app_model` default. `AnswerOptions` is the one exception, still on
  `exam_answeroptions`: renaming a table that already holds rows is a change worth making on its
  own, not as a side effect of adding a column.
- Booleans read as assertions: `is_published`, `has_expired`.
- Timestamps end in `_at`; **durations state their unit**: `duration_minutes`, never `duration`.

## Templates

- Extend `base.html`. Never duplicate the header, footer or theme tokens.
- Design tokens live in one place — the `@theme` block in `base.html`, mirrored in
  `static/css/input.css` for the production build. No one-off hex values.
- `{# … #}` comments a **single line only**. Multi-line needs `{% comment %}…{% endcomment %}`,
  or it renders as visible text on the page.
- **Never write a literal `<script>` inside a `{% comment %}` block.** Django strips the block, so
  the page is fine — but an editor's HTML parser does not know that. It sees an unclosed `script`,
  switches to raw-text mode, and reports every line after it as broken. Write "script element"
  instead. Other unclosed tags in comments are harmless; `script` is the one that swallows the
  rest of the file.
- **No `"` inside a `"`-delimited attribute**, even inside `{{ }}`. `|default:"objective"` within
  `x-data="…"` closes the attribute as far as any parser is concerned. Django accepts single-quoted
  filter arguments: `|default:'objective'`.
- A missing template variable renders as **empty string, silently**. Inside an Alpine expression
  that is not empty output but a syntax error, which kills the whole `x-data` and leaves the page
  inert.
- Reverse URLs by name — `{% url 'exam:book' %}` — never hardcode a path.

## Git

- Branch from `main`: `feat/…`, `fix/…`, `chore/…`.
- Small commits with a message saying *why*, not just what.
- Before merge: `manage.py check`, `manage.py makemigrations --check --dry-run`, and the tests
  once they exist.
