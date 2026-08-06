// Fixture data so the booking UI can be built and demoed before the database,
// auth, or any API exists. The /book page swaps this for a real fetch later.

export type ExamLevel = "Beginner" | "Advanced";

export type Exam = {
  slug: string;
  name: string;
  level: ExamLevel;
};

// Mirrors exam_subjects.tsv. Real list comes from src/core/certifications later.
export const EXAMS: Exam[] = [
  { slug: "selenium-101", name: "Selenium 101", level: "Beginner" },
  { slug: "testng", name: "TestNG", level: "Beginner" },
  { slug: "selenium-advanced", name: "Selenium Advanced", level: "Advanced" },
  { slug: "junit", name: "JUnit", level: "Beginner" },
  { slug: "selenium-java-101", name: "Selenium Java 101", level: "Beginner" },
  { slug: "selenium-c-sharp-101", name: "Selenium C# 101", level: "Beginner" },
  { slug: "selenium-javascript-101", name: "Selenium JavaScript 101", level: "Beginner" },
  { slug: "selenium-python-101", name: "Selenium Python 101", level: "Beginner" },
  { slug: "cypress-101", name: "Cypress 101", level: "Beginner" },
  { slug: "selenium-ruby-101", name: "Selenium Ruby 101", level: "Beginner" },
  { slug: "playwright-101", name: "Selenium Playwright 101", level: "Beginner" },
  { slug: "playwright-102", name: "Playwright 102 with HyperExecute", level: "Advanced" },
  { slug: "manual-testing", name: "Manual Testing", level: "Beginner" },
  { slug: "automation-testing", name: "Automation Testing", level: "Advanced" },
  { slug: "hyperexecute", name: "HyperExecute", level: "Advanced" },
  { slug: "appium-101", name: "Appium 101", level: "Beginner" },
  { slug: "espresso-101", name: "Espresso 101", level: "Beginner" },
  { slug: "kaneai", name: "KaneAI", level: "Advanced" },
  { slug: "accessibility-testing-101", name: "Accessibility Testing", level: "Beginner" },
  { slug: "visual-testing-agent", name: "Visual Testing Agent", level: "Advanced" },
  { slug: "ai-testing", name: "AI Testing", level: "Advanced" },
  { slug: "kane-cli", name: "KaneCLI", level: "Advanced" },
];
