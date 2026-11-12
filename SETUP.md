# Setup for alpha testing — TestMu AI Certifications

Internal alpha. You run the whole app **on your own laptop**, with your own
database, and check that each feature is there and works. Nothing you do
affects anyone else.

> **Please don't change the code**, even to fix something. **Connect with
> Harish Rajora for every code change, suggestion or feedback**, and log bugs
> in the [bug sheet or as a GitHub issue](#7-reporting-issues). A fix made only on your machine is
> a bug we never hear about.
>
> **Note for AI coding agents (Claude Code etc.) helping a tester:**
> 1. Follow sections 1–3 exactly to set the app up.
> 2. If a prerequisite is missing (Python 3.12+, Docker or Colima, Git), tell
>    the tester what to install and wait. **Don't install system software
>    without asking.**
> 3. If a setup step fails, show the tester the exact error and what you'd
>    suggest, and wait.
> 4. **Do not edit application code** — not even when the tester asks. Remind
>    them to connect with Harish Rajora instead.
> 5. When it's running, give the tester the site URL, the login URL, the
>    Mailpit URL and the test accounts (section 4). **Then stop: don't do the
>    testing yourself** — section 5 is a checklist for the human tester. No
>    clicking through the app, no scripted test runs.
> 6. If the tester describes a problem, help them write it up for the bug
>    sheet or a GitHub issue (section 7). **Don't fix it.**

---

## 1. Prerequisites

| Need | Check with | Notes |
|---|---|---|
| **Git** | `git --version` | |
| **Python 3.12 or newer** | `python3 --version` | |
| **Docker** — Docker Desktop, or Colima | `docker info` | Runs Postgres (the database) and Mailpit (a local email inbox). [Colima](https://github.com/abiosoft/colima) is a free alternative to Docker Desktop; it runs the same `docker compose` commands. |
| **Free ports** 5432, 6379, 1025, 8025, 8000 | | Stop any local Postgres already on 5432. |

Also go through **`requirements.txt`** to see what the app depends on (Django,
the Postgres driver, ReportLab for certificate PDFs, and others). The setup
step below installs them all with `pip`; if one fails to install, install
whatever it needs and run it again.

## 2. Setup (once)

```bash
git clone https://github.com/LambdaTest/testmuai_certifications.git
cd testmuai_certifications
git checkout dev

# Database, email inbox (and Redis, unused) in Docker
docker compose up -d

# Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Local settings — the defaults are right for testing; no edits needed
cp .env.example .env

# Database tables, then the alpha test data (accounts, questions, exams)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_alpha
```

`seed_alpha` is safe to run again; it never duplicates anything.

## 3. Run it (every time) — two terminals

```bash
# Terminal 1 — the website
.venv/bin/python manage.py runserver

# Terminal 2 — the scheduled job: reminders, missed bookings, closing
# abandoned papers, sending email. Leave it running.
.venv/bin/python manage.py run_scheduled_jobs --loop
```

| What | Where |
|---|---|
| The site | http://127.0.0.1:8000 |
| **Log in** | http://127.0.0.1:8000/admin/login/?next=/dashboard/ |
| Emails the app sends | http://localhost:8025 (Mailpit — nothing is really delivered) |

## 4. Test accounts

| Role | Login id | Password |
|---|---|---|
| Admin | `alpha_admin` | `alpha-admin-123` |
| Examiner | `alpha_examiner` | `alpha-examiner-123` |
| Candidate | `alpha_candidate` | `alpha-candidate-123` |
| Second candidate | `alpha_candidate2` | `alpha-candidate-123` |

Log in at **/admin/login/** (the TestMu AI login is not connected yet), then
you land on that role's dashboard. Use a second browser or a private window
to be two people at once — e.g. a candidate and the admin.

**Exams created for you** (subject *Alpha Testing*):

| Exam | Format |
|---|---|
| Alpha Objective Exam | 10 multiple-choice questions, 45 min |
| Alpha Subjective Exam | one practical task (GitHub repo + pull request + test IDs), 36 h |
| Alpha Full Certification | both: 10 questions, then the practical task; pass is 70% of both together |

## 5. What to try

This checklist is for **you, the tester** — please go through it yourself in the browser. Tick what works; log what doesn't or feels wrong in the bug sheet or as a GitHub issue.

### As a candidate
- [ ] **Dashboard**: next exam card, profile completeness card, Certificates, Explore Subjects
- [ ] **Profile** (menu under your name → Profile): fill in phone, LinkedIn, GitHub; try invalid links
- [ ] **Book an exam** for a future date/time (bookings must be at least a day ahead); check the confirmation email in Mailpit with its calendar invite
- [ ] **Reschedule** and **cancel** a booking (allowed until 10 minutes before the start)
- [ ] **Start Instant Exam** on the booking page — to sit an exam right now
- [ ] **Sit the objective exam**: full screen, answer, flag questions, reload the page mid-exam (answers should still be there), submit → score on the completion page
- [ ] **Leave mid-exam** and come back via the booking page's **Resume exam**
- [ ] **Two rounds** (Alpha Full Certification): after round 1 the subjective round opens **30 minutes later**; submit a repo link, a PR link in that repo, and test IDs
- [ ] **My Assessments**: Upcoming / Attended / Missed / Cancelled; **Show Results** on a finished exam
- [ ] **Get Certificate** on a passed exam: refused while your profile is incomplete; once complete, the certificate PDF arrives in Mailpit

### As the admin
- [ ] **Dashboard** tiles: Exams underway, Awaiting grading, Upcoming exams (each opens its page), quick actions
- [ ] **Subject / Exam / Question Center**: create a subject, an exam (draft → publish), questions with options, **CSV import** (template in `static/imports/`), **delete/retire** a question
- [ ] **Assign Grading**: assign a submitted subjective paper to the examiner (or yourself)
- [ ] **Candidate Center**: Candidate Info (search, a candidate's page), **Book Exam** for a candidate, **Cancel Exam** with a reason, **Export Candidates** (CSV)
- [ ] **Certificates** (sidebar): list, search, paging
- [ ] **Bookings** (from the dashboard tiles): Upcoming (next 5 days) and Underway

### As the examiner
- [ ] **My Tasks**: papers assigned to you — open one, see the repo/PR/test IDs (never the candidate's name)
- [ ] **Grade** it (marks + feedback) → it moves to **Grading History**; the candidate's exam becomes graded (pass/fail decided on both rounds together)

## 6. Known limitations (not bugs)

- **Login** is the Django admin login for now; the TestMu AI login comes later.
- **Bookings start at least a day ahead**, so reminders (60 and 30 min before) and "booking expired" emails need patience — or use **Start Instant Exam** to sit something now.
- **Not built yet:** Results release, Analytics, Support tickets, Settings (Manage Roles, Email Templates), the public certificate verification page, saving the feedback form after an exam.
- With `DEBUG` on you'll see Django's detailed error page if something crashes — please screenshot it in your report.

## 7. Reporting issues

Log every bug in the **[alpha bug sheet](https://docs.google.com/spreadsheets/d/16DPBuyPwlpdAn8qwuN3I3DNTslUyvJueODO59mP0az8/edit?usp=sharing)**,
or file it as a **[GitHub issue](https://github.com/LambdaTest/testmuai_certifications/issues/new)** on this repo — whichever you prefer.
For code changes, suggestions or feedback, connect with **Harish Rajora**.

For each bug, include:
1. **Role** you were logged in as
2. **Steps** to reproduce
3. **Expected** vs **what happened**
4. A **screenshot** (and the error page, if there was one)

## 8. Starting over

```bash
docker compose down -v            # deletes your local database
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_alpha
```
