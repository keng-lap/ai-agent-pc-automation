# Four-Agent Rollout Board

## Operating mode
This is a coordinator-managed Four-Agent workflow with four separated responsibilities. It is not four autonomous LLM processes and no runtime multi-agent orchestrator exists.

## Repository baseline and current status
- Repository: keng-lap/ai-agent-pc-automation
- Default branch: main
- Latest known main baseline before this planning branch: 7948103825fe1611e0663d7416c7aa02037d8439 (PR #38).
- PRs #30, #31, #32, #33, #35, #36, #37, and #38 are merged.
- Phase 3 closeout was explicitly approved by the Product Owner on 2026-10-30; all eight A4 acceptance criteria are recorded as met for the approved local/dry-run scope.
- Latest Product Owner-supplied Windows 11 test-script output: 100 backend tests passed, Ruff passed, 21 frontend tests passed. A4 did not independently execute this run.
- Phase 4 planning is authorized and underway. See docs/PHASE-4.md.
- Phase 4 runtime implementation has not started.
- Machine-changing operations remain dry-run/mock until Phase 5 is implemented and explicitly approved.
- No AI provider, provider credentials, live model calls, or external data transfer are approved.

## Roles
| Role | Responsibility | Phase 4 assignment |
|---|---|---|
| A1 — Coordinator / Product Analyst | Requirements, task decomposition, dependencies, integration, board | T-401 tool contract/catalog; T-403 task lifecycle; integration |
| A2 — Backend Engineer | Backend contracts, registry, validation, deterministic dispatch | Baseline gap analysis; T-402 after T-401 |
| A3 — Frontend / UX Engineer | Thai-default bilingual UX and API integration | UX flow notes; T-404 after API contract |
| A4 — QA / Security Reviewer | Threat model, test matrix, source/diff review, evidence | Contract review and T-405 test matrix/security review |

## Phase 4 task board
| ID | Owner | Deliverable | Dependencies | Status |
|---|---|---|---|---|
| T-401 | A1 + A2; A4 review | Tool contract/catalog for existing dry-run tools only | Phase 3 baseline | Planned |
| T-402 | A2; A4 review | Central registry, validation, deterministic dispatch; no new capability | T-401 | Planned |
| T-403 | A1 + A2; A4 review | Request-scoped in-memory task lifecycle; no persistence/history | T-401 | Planned |
| T-404 | A3; A4 review | Tool/task status and dry-run UX; Thai default, English option | T-401; T-402/T-403 API | Planned |
| T-405 | A4 | QA/security matrix and evidence review | T-401; implementation as available | Planned |
| T-406 | A1 + A4 | Integration/documentation closeout recommendation | T-402–T-405 | Blocked until verification |

## Parallelization and dependency rules
- A1 finalizes contracts and dependencies first.
- A2 may perform read-only source gap analysis in parallel; code changes wait for T-401.
- A3 may prepare UX notes against existing dry-run behavior; integration waits for stable API contracts.
- A4 may prepare threat model and test matrix in parallel; assertions trace to approved contracts.
- One task owns one branch and its files. Use separate working directories/worktrees for concurrent implementation.
- Branch naming for every task, including docs: <type>/<task-id>-<short-name>.
- Integrate in dependency order. No agent merges PRs.
- Product Owner approval remains required before merging code/runtime changes and before changing any approved decision or safety boundary.
- Documentation/planning may be completed without waiting for per-document approval when consistent with existing decisions and scope.

## Safety gates
- No arbitrary shell/PowerShell/script execution or raw model output execution.
- No real installation/removal, file changes, process actions, registry/system/network/security changes.
- No PC inspection or read-only discovery without separate proposal and approval.
- No provider integration, credentials, live model calls, or external data transfer.
- Preserve loopback binding and local API token enforcement.
- Do not persist chat messages/history or task history.
- Phase 5 remains mandatory before real machine-changing actions.

## Completed rollout history
- PR #30 — T-307 duplicate-token regression test — merged.
- PR #31 — T-306 Windows verification documentation — merged.
- PR #32 — MA-001 Four-Agent rollout board — merged.
- PR #33 — MA-005 board reconciliation and Phase 3 QA audit — merged.
- PR #35 — T-308 task-specific prerequisite planning — merged.
- PR #36 — T-308 polite install request parser correction — merged.
- PR #37 — T-308 post-merge verification documentation — merged.
- PR #38 — MA-006 Phase 3 closeout documentation reconciliation — merged.

## Definition of done
A task is complete when approved scope, tests/evidence, A4 review, documentation, and limitations are recorded. Code/runtime PRs require explicit Product Owner merge approval. Phase closeout requires explicit Product Owner approval.
