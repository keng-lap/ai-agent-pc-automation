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
**CLOSED — Product Owner approval recorded 2026-11-09.** P5-510–P5-515 are complete; the P5-515 matrix remains 33 Covered / 2 Partial (Q30 physical-device/screen-reader evidence deferred; Q35 Static Check limitation accepted). P5-516 findings are documented in `docs/P5-516-INDEPENDENT-SECURITY-REVIEW.md`; F-516-02 (#109) and F-516-03 (#108) are resolved. F-516-01 Google OIDC + authenticator-app TOTP implementation is merged (#114–#119; setup fixes #122–#127), and the Product Owner reports local testing passed. The targeted independent A4 review of the post-implementation F-516-01 changes remains unperformed and is explicitly accepted as a residual verification gap for closeout; it is not claimed as passed. P5-517 (#99) and P5-518 (#130) are merged. Full decision and limitations: `docs/P5-519-PHASE-5-CLOSEOUT-REPORT.md`. Phase 6 and real machine-changing execution remain unauthorized.

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
| 5 | **Complete — Product Owner closeout approved 2026-11-09.** F-516-01 targeted A4 follow-up remains an accepted residual verification gap; P5-515 retains 2 Partial items. P5-517 and P5-518 merged. Phase 6 unauthorized |
| 6 | Not Started |
| 7 | Not Started |
| 8 | Not Started |
| 9 | Not Started |
| 10 | Not Started |
