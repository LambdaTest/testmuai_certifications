"""
Seeds the certification catalog.

Deliberately a script rather than hand-entry through the admin: it is repeatable,
works for staging and fresh local databases, and is never wasted work.

    python manage.py seed_certifications
"""

from django.core.management.base import BaseCommand

from apps.exam.models import Certification

B = Certification.Level.BEGINNER
A = Certification.Level.ADVANCED

CERTIFICATIONS = [
    ("selenium-101", "Selenium 101", B),
    ("testng", "TestNG", B),
    ("selenium-advanced", "Selenium Advanced", A),
    ("junit", "JUnit", B),
    ("selenium-java-101", "Selenium Java 101", B),
    ("selenium-c-sharp-101", "Selenium C# 101", B),
    ("selenium-javascript-101", "Selenium JavaScript 101", B),
    ("selenium-python-101", "Selenium Python 101", B),
    ("cypress-101", "Cypress 101", B),
    ("selenium-ruby-101", "Selenium Ruby 101", B),
    ("playwright-101", "Selenium Playwright 101", B),
    ("playwright-102", "Playwright 102 with HyperExecute", A),
    ("manual-testing", "Manual Testing", B),
    ("automation-testing", "Automation Testing", A),
    ("hyperexecute", "HyperExecute", A),
    ("appium-101", "Appium 101", B),
    ("espresso-101", "Espresso 101", B),
    ("kaneai", "KaneAI", A),
    ("accessibility-testing-101", "Accessibility Testing", B),
    ("visual-testing-agent", "Visual Testing Agent", A),
    ("ai-testing", "AI Testing", A),
    ("kane-cli", "KaneCLI", A),
]


class Command(BaseCommand):
    help = "Create or update the certification catalog."

    def handle(self, *args, **options):
        created = updated = 0
        for slug, name, level in CERTIFICATIONS:
            _, was_created = Certification.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "level": level,
                    "status": Certification.Status.PUBLISHED,
                    "marketing_url": f"https://www.testmuai.com/certifications/{slug}/",
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"{created} created, {updated} updated."))
