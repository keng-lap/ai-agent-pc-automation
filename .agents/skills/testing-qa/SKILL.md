---
name: testing-qa
description: Plan, run, or review automated tests and quality evidence for this repository, including backend tests, Angular unit tests, Playwright desktop E2E, CI, accessibility, and regression checks.
---

# Testing and QA

## Test selection
- Read the task acceptance criteria and existing test scripts before choosing commands.
- Prefer the smallest relevant test first, then required regression/build checks.
- Report exact command, observed result, and environment. Never invent counts or infer a pass from a report server starting.
- Distinguish test execution from opening/viewing an HTML report.

## Current boundaries
- Playwright Q30 coverage is desktop localhost only (1920x1080, 1366x768, 1280x720 plus existing UI assertions). Do not claim mobile-device, screen-reader, or broad accessibility coverage from it.
- Mobile and screen-reader evidence remain separate gaps unless newer verified evidence closes them.
- Static checks are not a runtime sandbox. Static analysis cannot prove runtime isolation or prevent all side effects.
- Do not run tests that inspect or change the real Windows machine, install/uninstall software, modify files outside the test fixture, execute shell commands through the product, or access external services unless a bounded task explicitly authorizes it.
- Keep tests deterministic, local, and isolated. Mock machine-changing behavior.

## Evidence format
Summarize: command; pass/fail and count if actually shown; relevant environment; skipped/not-run checks; known limitations. Preserve failure output needed to debug.
