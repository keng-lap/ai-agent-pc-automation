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
**P5-510–P5-514 complete and merged (PRs #58–#65). P5-515 closeout approved by the Product Owner on 2026-11-08 and recorded in `docs/P5-515-CLOSEOUT-REPORT.md`. The matrix remains 33 Covered / 2 Partial / 0 Not covered. Q30 remains Partial pending physical-device and screen-reader results. The Product Owner accepted the Q35 limitation that Static Check is not a Runtime Sandbox; Q35 remains Partial technically and no runtime sandbox is in scope. Final A4 reconciliation is complete. Q30 physical-device/screen-reader evidence is deferred and remains Partial; Q35 remains Partial under the accepted Static Check limitation. P5-516 independent review has not started and remains separately gated.** Phase 5 remains a mandatory safety gate; Phase 6 and real machine-changing execution remain unauthorized. See docs/PHASE-5.md and docs/P5-515-REMAINING-GAP-CLOSURE-PLAN.md.

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
- T-601 separately authorizes Gemini text-only chat and temporary context (2026-11-03): the current message plus up to 10 recent user/assistant pairs may be sent to Gemini. Context remains in backend process memory, expires after 1 hour of inactivity, is not written to disk or browser storage, and can be cleared by the user. The API key remains in backend memory only; function/tool calling and PC actions remain disabled. Any broader provider integration or external data flow still requires explicit Product Owner decisions.
- Phase closeout requires evidence and explicit Product Owner approval.

## Current position
| Phase | Status |
|---|---|
| 0 | Complete |
| 1 | Complete |
| 2 | Complete |
| 3 | Complete — closeout approved |
| 4 | Complete — Product Owner closeout approved 2026-11-02 |
| 5 | P5-510–P5-514 complete; P5-515 closed with PO approval (2026-11-08), 33 Covered / 2 Partial; Q30 evidence deferred and Q35 limitation accepted; P5-516 gated/not started; real execution not authorized |
| 6 | Not Started |
| 7 | Not Started |
| 8 | Not Started |
| 9 | Not Started |
| 10 | Not Started |
