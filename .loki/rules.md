# LOKI Business Rules for the Bundled Playground

> These rules belong to LOKI's own test target, `playground/index.html`, and are what LOKI's CI
> (`.github/workflows/loki.yml`) evaluates against it. They are **not** rules for your project:
> `loki init` generates a fresh `.loki/rules.md` in your repository for that.

LOKI evaluates these criteria during stress testing and exploratory sessions.

## Critical Business Assertions
- Action buttons must disable upon click to prevent concurrent double-submissions.
- Unhandled JavaScript exceptions in the browser console are classified as critical failures.
- Forms must display contextual error banners rather than blank pages or unstyled crash screens.
- Financial transactions (payments, transfers) must have deterministic server idempotency locks.
