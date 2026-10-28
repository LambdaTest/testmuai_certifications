# Routes

What exists today, what is planned, and where new URLs belong.

## Where URLs live

Each app owns a `urls.py`, included from `config/urls.py` at the root. There is no path prefix per
app — `apps.exam` and `apps.home` both mount at `/`, so URL *names* are what keep them apart:

```python
{% url 'exam:book' %}          # /book/
{% url 'home:dashboard' %}     # /dashboard/
```

**Always reverse by name, never hardcode a path.** Several routes have already moved during the
build; every one that used `{% url %}` survived the move untouched.

## Built today

### Candidate

| URL | Name | View |
|---|---|---|
| `/` | `home:index` | Redirects to `/book/` |
| `/dashboard/` | `home:dashboard` | Routes by role — candidate, admin or examiner |
| `/book/` | `exam:book` | Entry point from the main site. Exam selector, then date and time. |
| `/start_instant_exam/` | `exam:start_instant_exam` | **POST only.** Start Instant Exam: books the chosen exam for now, then redirects to its T&C page. Posted by the booking page's own form (`formaction`). |
| `/myassessments/<status>` | `exam:myassessment` | Bookings by bucket — upcoming (`booked`), no-show, attended, cancelled |
| `/assessment/<uuid>` | `exam:explore_assessment` | One booking in detail |
| `/bookings/<uuid>/reschedule/` | `exam:reschedule` | Move a booking to a new slot |
| `/bookings/<uuid>/cancelpage/` | `exam:cancel_booking_page` | Cancellation confirmation |
| `/bookings/<uuid>/cancel/` | `exam:cancel_booking` | **POST** cancels |
| `/bookings/<uuid>/calendar.ics` | `exam:booking_ics` | Calendar invite download, at the booking's current sequence |

### Exam player

| URL | Name | View |
|---|---|---|
| `/exam/player/<uuid>/termsandconditions/` | `exam:start_exam_termsandconditions` | Instructions. **POST** is "I'm ready to begin": draws the paper, starts the clock, marks the booking attended. Also how a candidate who dropped out resumes. |
| `/exam/player/<uuid>/` | `exam:exam_player` | The objective player — full screen, timed, review flags |
| `/exam/player/<uuid>/save/` | `exam:save_answer` | **POST**, from the player's JavaScript: autosaves one answer, flag and position |
| `/exam/player/subjective/<uuid>/` | `exam:exam_player_subjective` | The subjective round — repository, pull request, test IDs |
| `/exam/player/<uuid>/submit/` | `exam:submit_exam` | **POST** submits either round |
| `/exam/player/<uuid>/completed/` | `exam:exam_completed` | Completion page; the score for an objective round |

The instructions page POSTs to begin rather than linking. Beginning draws the paper and starts the
clock — a GET that did that would be one browser prefetch away from starting somebody's exam.

The player deliberately renders **no navigation**: a nav bar mid-exam is an invitation to leave,
and it muddies "did the candidate navigate away" telemetry.

### Grading (admins and examiners)

| URL | Name | View |
|---|---|---|
| `/assign_grading_page/` | `exam:assign_grading_template` | Admin only. Papers under review, assign or unassign each |
| `/assign_grading/<uuid>/` | `exam:assign_grading` | Admin only, **POST** |
| `/my_tasks/` | `exam:my_tasks` | Papers assigned to the viewer, still under review |
| `/grading_page/<uuid>/` | `exam:grading_page` | One paper, blind — the task and the candidate's answer, never their identity |
| `/grade_an_exam/<uuid>/` | `exam:grade_an_exam` | **POST** saves the grade |
| `/grading_history/` | `exam:grading_history` | What the viewer has graded, read-only |

Shared pages take the layout from the view (`base_staff.html` for admins, `base_examiner.html` for
examiners), so each role keeps its own sidebar.

### Admin authoring

All behind `@role_required(User.Role.ADMIN)`, all extending `base_staff.html` with its accordion
sidebar. Grouped by "center" to match the sidebar, which is why the paths carry that prefix.

| URL | Name | View |
|---|---|---|
| `/subject_center/explore_subjects/` | `exam:explore_subjects` | Subject list with live filter |
| `/subject_center/create_subject/` | `exam:create_subject` | New subject; slug derived if blank |
| `/subject_center/edit_subject/<int>/` | `exam:edit_subject` | Edit in place |
| `/exam_center/explore_exams/` | `exam:explore_exams` | Exam list, drafts first |
| `/exam_center/add_exam/` | `exam:add_exam` | Create; the button pressed decides draft or published |
| `/exam_center/edit_exam/<int>/` | `exam:edit_exam` | Same form and template as add |
| `/question_center/question_bank/` | `exam:question_bank` | Read-only bank; cards expand |
| `/question_center/add_question/` | `exam:add_question` | Question + answer options + media, one POST |
| `/question_center/import_questions/` | `exam:import_questions` | CSV import. Upload previews; a second POST with `action=import` commits. |
| `/question_center/delete_question/<int>/` | `exam:delete_question` | **Routed, stubbed.** See `TRACKER.md` for the gated-delete design. |

**One URL, two phases, on the importer.** Uploading a file and confirming the import are both
POSTs to the same path; `action=import` distinguishes them, and the parsed rows wait in the
session between the two. A separate confirm URL would need the file posted twice.

### Candidate Center (admins only)

The one place a booking reference turns back into a person — never opened to examiners, which is
what keeps grading blind.

| URL | Name | View |
|---|---|---|
| `/candidates/` | `home:candidate_info` | Search (name, email, login id, phone, booking reference), 25 per page |
| `/candidate_detail/<int>/` | `home:candidate_detail` | One candidate: profile and every booking, with Cancel links and cancellation details |
| `/book_exam_admin/` | `exam:book_exam_admin` | Book on a candidate's behalf. GET shows, POST books; `?candidate=` pre-fills |
| `/cancel_exam_admin/` | `exam:cancel_exam_admin_search` | Exact-match search (email, login id, booking reference) for cancellable bookings |
| `/cancel_exam_admin/<uuid>/` | `exam:cancel_exam_admin_confirm` | Confirm with a reason. GET shows, POST cancels |
| `/export_candidates/` | `home:export_candidates` | CSV export. GET shows; `?download=…` sends the file |

**Integer ids in admin routes, UUIDs in candidate-facing ones.** Admin routes sit behind a role
check, so enumeration buys nothing — a subject or user id is not a secret the way a booking
reference is.

### Django admin

`/admin/` — the built-in admin, registered for `User`, `Subject`, `Question`, `Exam`,
`ExamBooking`, `Image`, `Audio`, `Video` and `ExamSheetQuestion`. Also the only way to log in until
the OIDC integration lands.

> **`ExamSheetQuestion` is registered** (`apps/exam/admin.py`). An earlier rule kept it — and
> `ExamSheet` — out of the admin, because editing a paper a candidate has sat is exactly what the
> immutability design exists to prevent, and the admin bypasses form validation. Decide whether the
> registration stays (read-only would keep the rule) — see `TRACKER.md`.

## Not built

**Results** — release of graded and combined results, and the score report; the "Show Results"
button on a booking still has no route.

**Unlinked admin destinations** — the dashboard tiles, Certificates, Analytics, Manage Roles and
Email Templates are still `href="#"` in `base_staff.html`.

**Public credential verification** — `/verify/<credential-id>`. Anonymous, indexable, and the
canonical credential rather than a PDF. Must show revoked and expired states unmistakably, and
never expose email, score or attempt history.

**Auth** — `/auth/login`, `/auth/callback`, `/auth/logout`. No sign-in page: identity comes from
TestMu AI's existing login. See [`auth.md`](auth.md).

## Rules for new routes

**Ownership goes in the lookup, not a check afterwards.**

```python
booking = get_object_or_404(ExamBooking, booking_id=booking_id, candidate=request.user)
```

Another candidate's UUID then returns **404, not 403** — we don't confirm a booking exists to
someone with no business knowing. Every booking view does this.

**Gate candidate pages on ownership, staff pages on role.** Candidate routes find the booking by
id *and* owner, never by checking a role. Staff routes use `@role_required(...)`
(`apps/home/decorators.py`), which returns 404 rather than 403 to anyone else.

**Anything that mutates is a POST.** Cancellation lives at `cancel_booking` behind a POST with a
CSRF token; the GET on the same URL only renders the confirmation. A destructive GET can be
triggered by browser prefetch, link previews and mail scanners.

**Redirect after a successful POST.** `book()` saves and returns a 302 rather than rendering,
because a reload repeats the last request — and a repeated POST creates a second booking. A
success message travels with the redirect through `messages`.

**One view for show-and-save where it fits.** `book_exam_admin` and `cancel_exam_admin_confirm`
are a GET that shows the page and a POST that saves, building the form with
`request.POST or None` — so the GET form is unbound and shows no errors.

**UUIDs in candidate-facing paths, integers behind a role check.** `<uuid:booking_id>` guarantees
a real UUID before the view runs, and booking references are not enumerable — which matters
because a booking id is the thing an examiner sees instead of a candidate's name. Admin authoring
routes use `<int:...>`: they sit behind `@role_required`, and a subject id is not a secret.

## Out of scope

**The catalogue.** Browsing certifications lives on the main TestMu AI site. Its cards land the
candidate on `/book`, which takes no path parameter — they choose from a selector. Their catalogue
is single-select, which isn't flexible enough once someone changes their mind or arrives by
bookmark. No URL contract with the main site, so they can restructure freely.

**Login.** No sign-in, sign-up, forgot-password or reset pages, and no password hashes in our
database. Authentication is the only integration between the two systems — there is no entitlement
sync, registration webhook or catalogue API. Booking *is* enrolment.
