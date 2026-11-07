---
name: project-context
description: Establish the current project state, scope, phase, approved decisions, and handoff before planning or changing this repository. Use at the start of a project session or when asked for status, next steps, or scope.
---

# Project Context

## Required checks
1. Read `GEMINI.md`, `README.md`, `docs/PROJECT.md`, `docs/ROADMAP.md`, the active phase/task document, and relevant approved decisions.
2. Inspect current Git branch/status and latest `main`; inspect relevant open/merged PRs and CI before reporting status.
3. Treat repository records as source of truth. Do not rely on chat memory when current repository evidence is available.
4. Resolve conflicts by identifying them. Prefer explicit Product Owner decisions and current approved task documents; never silently choose between conflicting requirements.

## Scope rules
- Distinguish completed, merged, CI-verified, locally verified, and still-open work.
- Treat proposals, assumptions, and examples as non-binding until approved.
- Do not skip phases or infer authorization for the next task from completion of the previous task.
- Current product scope is local-first on Windows 11 and loopback/local network only as explicitly approved. Do not add public remote access or mobile remote PC control.
- Phase 6 and real PC execution require separate explicit authorization. Current machine-changing tools remain dry-run/mock unless a newer approved decision says otherwise.

## Communication
- Communicate with the Product Owner in concise Thai by default.
- Ask only for a genuinely blocking Product Owner decision. Use safe, reversible defaults for routine details and state material assumptions.
- Give a maximum five-bullet checkpoint: current phase/task, verified completed work, open gaps, blockers/approval gates, next bounded step.
