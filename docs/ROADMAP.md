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
**Complete — Product Owner closeout approved 2026-11-02.** T-402, T-403, and T-404 runtime implementation merged in PRs #45–#47. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed. Verification commit: 8233af5. See docs/PHASE-4.md.

## Phase 5 — Safety and Permission System
**Planning authorized 2026-11-02; P5-510 complete, P5-511 authorized/in progress.** Runtime authorization is per bounded task. Phase 5 remains a mandatory safety gate before real machine-changing operations and does not authorize Phase 6 execution. See docs/PHASE-5.md.

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
- T-601 separately authorizes Gemini text-only chat (2026-11-03): current message only, no chat-history transfer or function/tool calling, and API key in backend memory only. Any broader provider integration or external data flow still requires explicit Product Owner decisions.
- Phase closeout requires evidence and explicit Product Owner approval.

## Current position
| Phase | Status |
|---|---|
| 0 | Complete |
| 1 | Complete |
| 2 | Complete |
| 3 | Complete — closeout approved |
| 4 | Complete — Product Owner closeout approved 2026-11-02 |
| 5 | P5-510 complete; P5-511 authorized/in progress; real execution not authorized |
| 6 | Not Started |
| 7 | Not Started |
| 8 | Not Started |
| 9 | Not Started |
| 10 | Not Started |
