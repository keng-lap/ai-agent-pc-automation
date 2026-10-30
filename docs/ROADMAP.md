# Project Roadmap

The project is developed incrementally. Each phase has a defined scope, safety boundary, verification evidence, and explicit Product Owner closeout. The approved phase order is preserved.

## Phase 0 — Foundation
**Complete.** See docs/PHASE-0.md.

## Phase 1 — Local Development Environment
**Complete.** See docs/PHASE-1.md.

## Phase 2 — Local Web Application
**Complete (2026-10-23).** T-202, T-203, T-205, and T-204 are merged. The Product Owner reported MV-01 to MV-14 passed. See docs/PHASE-2-COMPLETION-REPORT.md.

## Phase 3 — Agent Core
**Complete — Product Owner closeout approved 2026-10-30.** T-301 through T-308 are merged. T-308 adds task-specific prerequisite records and deterministic tests (PR #35); PR #36 fixes polite install request parsing. A4's final reassessment marks all eight acceptance criteria met for the approved local/dry-run scope. Product Owner-supplied Windows 11 test-script evidence: 100 backend tests passed, Ruff passed, 21 frontend tests passed. A4 did not independently execute this Windows run. See docs/PHASE-3-QA-REVIEW.md, docs/T-308-REPORT.md, and docs/PHASE-3.md.

## Phase 4 — Tool / Task System
**Status: Planning authorized; runtime implementation not started.** The Product Owner authorized Phase 4 planning after Phase 3 closeout. Detailed plan: docs/PHASE-4.md.

Goal: formalize a backend-controlled tool catalog, validation/dispatch boundary, request-scoped task lifecycle, and clear dry-run status UX.

Proposed tasks:
- T-401 — Tool contract/catalog for existing dry-run tools.
- T-402 — Central registry, validation, deterministic dispatch.
- T-403 — Request-scoped in-memory task lifecycle; no history persistence.
- T-404 — Thai-default bilingual tool/task status UX.
- T-405 — QA/security matrix and evidence.
- T-406 — Integration and Phase 4 closeout recommendation.

Safety boundary: no real installation/removal, shell execution, file/process/system changes, PC inspection, provider integration, credentials, or external data transfer. All machine-changing paths remain mock/dry-run until Phase 5 is complete and explicitly approved.

## Phase 5 — Safety and Permission System
**Not Started.** Mandatory safety gate before real machine-changing operations. Scope includes risk classification, explicit confirmation, permission levels, parameter validation, command restrictions, and audit controls.

## Phase 6 — Real PC Automation
**Not Started.** Any real PC-changing execution is blocked until Phase 5 is complete and explicitly approved, and each tool is separately authorized.

## Phase 7 — Monitoring and Logging
**Not Started.** Future observability scope must respect data minimization and explicit retention decisions.

## Phase 8 — Reliability
**Not Started.**

## Phase 9 — Advanced Agent
**Not Started.** Multi-step planning, memory, scheduled/background tasks, and autonomy require separate privacy, safety, and architecture decisions.

## Phase 10 — Production-Ready Personal Agent
**Not Started.**

## Development and approval rules
- Never skip or reorder phases without an explicit Product Owner decision.
- Documentation/planning can proceed without per-document approval when consistent with approved decisions and current scope.
- Runtime/code changes require bounded tasks, tests, review, and explicit Product Owner merge approval.
- No real PC-changing action before Phase 5 is complete and explicitly approved.
- No provider integration or external data transfer without explicit decisions on provider, account authorization, data handling, and secure credential storage.
- Phase closeout requires evidence and explicit Product Owner approval.

## Current position
| Phase | Status |
|---|---|
| 0 | Complete |
| 1 | Complete |
| 2 | Complete |
| 3 | Complete — closeout approved |
| 4 | Planning authorized; implementation not started |
| 5 | Not Started |
| 6 | Not Started |
| 7 | Not Started |
| 8 | Not Started |
| 9 | Not Started |
| 10 | Not Started |
