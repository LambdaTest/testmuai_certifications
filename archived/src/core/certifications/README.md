# core/certifications

Certification products and their versioned exam blueprints. **This app is the source of truth** —
the main TestMu AI site holds only marketing pages on top.

## Two levels, don't conflate them

- **Certification** — the product. "Accessibility Testing 101". Long-lived, publicly named,
  rarely changes. Carries name, slug, level, description, icon.
- **Exam version** — a blueprint for testing it: sections, selected questions, weights, duration,
  pass mark. Versioned because the exam evolves while the certification does not.

An attempt always references an **exam version**, never a certification directly. That is what
lets you explain a result from two years ago.

## Slugs

Use the same slug strings the main site already uses in its URLs
(`testmuai.com/certifications/accessibility-testing-101/`). This requires nothing from them — we
simply choose matching values — and it gives both systems one vocabulary for support, analytics,
and any future integration. Slugs are stable identifiers, not display strings.

## `external_ref` — insurance for later integration

Carry a **nullable `external_ref`** column from the first migration.

Integration with the main site is deliberately deferred until the build is done. When it happens,
they may pass an exam identifier that is our slug, their own internal ID, or a display name like
"Accessibility Testing 101" — nobody knows yet. A nullable column absorbs any of those without a
migration or a hunt through the codebase.

It costs one column now. Leave it null until integration.

## Publishing freezes a version

Once an exam version is published and attempted, it is **immutable**. Edits create a new version;
they never mutate a published one. A candidate disputing a result is entitled to see the exam
exactly as it was served.

This is the rule most likely to be broken by a well-meaning "quick fix to a typo in a published
question". Enforce it in code and with a database constraint.

## Bookable certifications

The `/book` selector needs "what can this candidate book right now" — not `SELECT *`. Filter to
certifications that are published, have a slot with open registration and remaining capacity, and
that this candidate is eligible for (no active cooldown, not already passed, prerequisites met).

Keep that query here, not in the page.
