"""
Sets up a fresh local database for alpha testing:

    python manage.py seed_alpha

Creates test accounts for every role (with the passwords listed in
SETUP.md), one subject, a bank of questions, and three published
exams — objective only, subjective only, and two rounds — each with enough
questions to actually be sat.

Safe to run again: anything that already exists is left as it is (passwords
are not reset), so it never doubles the questions or overwrites a tester's
changes.

LOCAL TESTING ONLY. The accounts have fixed, published passwords and are
staff (Django-admin login is the only login until the TestMu AI login is
built), so never run this against a shared or production database.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exam.models import AnswerOptions, Exam, Question, Subject
from apps.home.models import User

#: (login id, display name, email, role, password) — the same table as
#: SETUP.md. Change both together.
ACCOUNTS = [
    ("alpha_admin", "Alpha Admin", "alpha.admin@example.com", User.Role.ADMIN, "alpha-admin-123"),
    ("alpha_examiner", "Alpha Examiner", "alpha.examiner@example.com", User.Role.EXAMINER, "alpha-examiner-123"),
    ("alpha_candidate", "Alpha Candidate", "alpha.candidate@example.com", User.Role.CANDIDATE, "alpha-candidate-123"),
    ("alpha_candidate2", "Second Candidate", "alpha.candidate2@example.com", User.Role.CANDIDATE, "alpha-candidate-123"),
]

SUBJECT = ("Alpha Testing", "alpha-testing", "Sample subject for alpha testing: software testing fundamentals.")

#: (question, [options], index of the correct option) — 15, so a 10-question
#: paper is a real random draw.
OBJECTIVE_QUESTIONS = [
    ("Which Selenium WebDriver method finds a single element on the page?",
     ["find_element", "find_elements", "get_element", "locate"], 0),
    ("What does a 404 HTTP status code mean?",
     ["Server error", "Not found", "Unauthorised", "Redirect"], 1),
    ("Which kind of testing checks that a recent change did not break existing features?",
     ["Smoke testing", "Load testing", "Regression testing", "Usability testing"], 2),
    ("In Playwright, what does page.goto() do?",
     ["Clicks a link", "Opens a URL in the page", "Goes back in history", "Closes the page"], 1),
    ("Which locator is usually the most stable for automation?",
     ["Absolute XPath", "A dedicated test id attribute", "Element position on screen", "Text of a random div"], 1),
    ("What is the main purpose of a test assertion?",
     ["Start the browser", "Compare actual and expected results", "Wait for an element", "Log in a user"], 1),
    ("Which of these is a headless browser mode?",
     ["Running without a visible window", "Running with two windows", "Running on a phone only", "Running with images off"], 0),
    ("What does CI stand for in software delivery?",
     ["Continuous Integration", "Code Inspection", "Central Infrastructure", "Coverage Index"], 0),
    ("Which HTTP method is normally used to create a resource in a REST API?",
     ["GET", "DELETE", "POST", "HEAD"], 2),
    ("What is a flaky test?",
     ["A test that always fails", "A test that passes and fails without code changes", "A test with no assertions", "A test that runs slowly"], 1),
    ("Which wait is better practice than a fixed sleep in UI automation?",
     ["Explicit wait for a condition", "Sleeping 10 seconds", "Reloading the page", "Restarting the browser"], 0),
    ("Cross-browser testing checks that an app…",
     ["Works the same across browsers", "Loads faster", "Uses less memory", "Has no bugs"], 0),
    ("What is the purpose of a test case's 'expected result'?",
     ["Describe setup steps", "State what should happen", "List the test data", "Name the tester"], 1),
    ("Which tool is commonly used for API testing?",
     ["Postman", "Photoshop", "Excel", "Figma"], 0),
    ("A smoke test is typically…",
     ["A full regression suite", "A quick check that the main features work", "A security audit", "A performance benchmark"], 1),
]

#: Subjective tasks — answered with a GitHub repo, a pull request and test IDs.
SUBJECTIVE_TASKS = [
    "Write an automated UI test suite for a login page: one test for a successful login, one for a wrong "
    "password, and one for an empty form. Push it to a GitHub repository and open a pull request with your "
    "tests. Submit the repository link, the pull request link and your test IDs.",
    "Write API tests for a public JSON API of your choice: check a successful GET, a 404 for a missing "
    "resource, and the shape of the response body. Push them to a GitHub repository, open a pull request, and "
    "submit the links and your test IDs.",
]

EXAMS = [
    # (name, slug, type, level, objective question count, description)
    ("Alpha Objective Exam", "alpha-objective", Exam.Type.OBJECTIVE, Exam.Level.BEGINNER, 10,
     "Objective only: 10 multiple-choice questions, 45 minutes."),
    ("Alpha Subjective Exam", "alpha-subjective", Exam.Type.SUBJECTIVE, Exam.Level.INTERMEDIATE, None,
     "Subjective only: one practical task, submitted within 36 hours, graded by an examiner."),
    ("Alpha Full Certification", "alpha-full", Exam.Type.BOTH, Exam.Level.INTERMEDIATE, 10,
     "Two rounds: 10 multiple-choice questions, then a practical task. Pass is 70% of both together."),
]


class Command(BaseCommand):
    help = "Seed a fresh local database for alpha testing (accounts, subject, questions, exams). Local use only."

    @transaction.atomic
    def handle(self, *args, **options):
        users = {}
        for ext, name, email, role, password in ACCOUNTS:
            user = User.objects.filter(external_id=ext).first()
            if user is None:
                user = User.objects.create_user(
                    external_id=ext, email=email, display_name=name, role=role, is_staff=True,
                )
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(f"  account  {ext:18} ({role}) created")
            else:
                self.stdout.write(f"  account  {ext:18} already exists — left as it is")
            users[ext] = user
        admin = users["alpha_admin"]

        name, slug, description = SUBJECT
        subject, created = Subject.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": description, "created_by": admin},
        )
        self.stdout.write(f"  subject  {name} {'created' if created else 'already exists'}")

        added = 0
        for text, options, correct in OBJECTIVE_QUESTIONS:
            question, created = Question.objects.get_or_create(
                question_text=text, question_subject=subject,
                defaults={"created_by": admin, "question_type": Question.Type.OBJECTIVE, "marks": Exam.MARKS_PER_QUESTION},
            )
            if created:
                added += 1
                for i, option in enumerate(options):
                    AnswerOptions.objects.create(
                        question=question, answer_option_text=option, is_correct=(i == correct), created_by=admin,
                    )
        for text in SUBJECTIVE_TASKS:
            _, created = Question.objects.get_or_create(
                question_text=text, question_subject=subject,
                defaults={"created_by": admin, "question_type": Question.Type.SUBJECTIVE, "marks": Exam.SUBJECTIVE_MARKS},
            )
            added += created
        self.stdout.write(f"  questions {added} added "
                          f"({len(OBJECTIVE_QUESTIONS)} objective and {len(SUBJECTIVE_TASKS)} subjective in the bank)")

        for exam_name, exam_slug, exam_type, level, count, exam_description in EXAMS:
            exam, created = Exam.objects.get_or_create(
                slug=exam_slug,
                defaults={
                    "exam_name": exam_name, "subject": subject, "exam_type": exam_type, "exam_level": level,
                    "question_count": count, "description": exam_description,
                    "status": Exam.Status.PUBLISHED, "created_by": admin,
                },
            )
            self.stdout.write(f"  exam     {exam_name:26} {'created, published' if created else 'already exists'}")

        if not Question.objects.filter(question_subject=subject, question_type=Question.Type.OBJECTIVE).count() >= 10:
            raise CommandError("Not enough objective questions to sit a 10-question paper.")
        self.stdout.write(self.style.SUCCESS("Alpha data ready. Logins are in SETUP.md."))
