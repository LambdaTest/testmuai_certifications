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
| `/` | `home:index` | Redirects to the dashboard |
| `/dashboard/` | `home:dashboard` | Routes by role — candidate, admin or examiner |
| `/book/` | `exam:book` | Entry point from the main site. Exam selector, then date and time. |
| `/myassessments/<status>` | `exam:myassessment` | Bookings filtered by status |
| `/assessment/<uuid>` | `exam:explore_assessment` | One booking in detail |
| `/bookings/<uuid>/reschedule/` | `exam:reschedule` | Move a booking to a new slot |
| `/bookings/<uuid>/cancelpage/` | `exam:cancel_booking_page` | Cancellation confirmation |
| `/bookings/<uuid>/cancel/` | `exam:cancel_booking` | **POST** cancels. GET renders the confirmation. |
| `/bookings/<uuid>/calendar.ics` | `exam:booking_ics` | Calendar invite download |

### Django admin

`/admin/` — the built-in admin, registered for `User`, `Subject`, `Exam`, `Question`,
`AnswerOptions`, `Image`, `Audio` and `Video`. Also the only way to log in until the OIDC
integration lands.

## Not built

**Exam player** — `/exam/<uuid>/instructions`, `/exam/<uuid>`, `/exam/<uuid>/submitted`.
Deliberately renders **no navigation**: a nav bar mid-exam is an invitation to leave, and it
muddies "did the candidate navigate away" telemetry. Support must be reachable from inside the
exam without navigating away — a panel, not a link.

**Custom admin** — the dashboard template exists (`home/dashboard_admin.html`) but every link is
`#`. Planned sections: My Tasks, Exam Center, Question Center, Subject Center, Candidate Center,
Certificates, Analytics, Settings, Support Tickets.

**Examiner** — a pending-evaluations list plus Grading History, Settings and Support Tickets.
Separate templates from the admin rather than conditionals: an examiner should be structurally
unable to render admin controls.

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

**Gate on ownership, not role.** `role` is checked in exactly one place, the dashboard router.
Keeping it that way is what makes the eventual multi-role change cheap, and it means an examiner
can book an exam like anyone else.

**Anything that mutates is a POST.** Cancellation lives at `cancel_booking` behind a POST with a
CSRF token; the GET on the same URL only renders the confirmation. A destructive GET can be
triggered by browser prefetch, link previews and mail scanners.

**Redirect after a successful POST.** `book()` saves and returns a 302 rather than rendering,
because a reload repeats the last request — and a repeated POST creates a second booking.

**UUIDs in paths, not sequential ids.** `<uuid:booking_id>` guarantees a real UUID before the
view runs, and booking ids aren't enumerable.

## Out of scope

**The catalogue.** Browsing certifications lives on the main TestMu AI site. Its cards land the
candidate on `/book`, which takes no path parameter — they choose from a selector. Their catalogue
is single-select, which isn't flexible enough once someone changes their mind or arrives by
bookmark. No URL contract with the main site, so they can restructure freely.

**Login.** No sign-in, sign-up, forgot-password or reset pages, and no password hashes in our
database. Authentication is the only integration between the two systems — there is no entitlement
sync, registration webhook or catalogue API. Booking *is* enrolment.
