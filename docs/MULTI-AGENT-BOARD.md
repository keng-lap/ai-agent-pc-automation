# Four-Agent Rollout Board

## Operating mode
This is a coordinator-managed Four-Agent workflow with four separated responsibilities. It is not four autonomous LLM processes and no runtime multi-agent orchestrator exists.

## Repository baseline and current status
- Repository: keng-lap/ai-agent-pc-automation
- Default branch: main
- Latest main baseline at Phase 4 closeout: 8233af5a9f29a61a20d86a1662c88dd0274578f9.
- Phase 4 closeout was explicitly approved by the Product Owner on 2026-11-02.
- Phase 4 implementation PRs #45–#47 are merged. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed.
- Phase 5 planning was authorized by the Product Owner on 2026-11-02. Planning baseline: docs/PHASE-5.md.
- No Phase 5 runtime implementation, permission grant, or real PC execution is authorized yet.
- Machine-changing operations remain dry-run/mock until Phase 5 is complete and explicitly approved; Phase 6 and each capability require separate authorization.
- No AI provider, provider credentials, live model calls, or external data transfer are approved.

## Roles
| Role | Responsibility | Phase 4 assignment |
|---|---|---|
| A1 — Coordinator / Product Analyst | Requirements, task decomposition, dependencies, integration, board | T-401 tool contract/catalog; T-403 task lifecycle; integration |
| A2 — Backend Engineer | Backend contracts, registry, validation, deterministic dispatch | Baseline gap analysis; T-402 after T-401 |
| A3 — Frontend / UX Engineer | Thai-default bilingual UX and API integration | UX flow notes; T-404 after API contract |
| A4 — QA / Security Reviewer | Threat model, test matrix, source/diff review, evidence | Contract review and T-405 test matrix/security review |

## Phase 4 closeout
Phase 4 is complete. PRs #45–#47 are merged; the Product Owner's focused Windows verification passed. See docs/PHASE-4.md.

## Phase 5 planning board
See docs/PHASE-5.md for P5-501 through P5-508, dependencies, workstream assignments, and the planning-only safety boundary.

## Archived Phase 4 task board
| ID | Owner | Deliverable | Dependencies | Status |
|---|---|---|---|---|
| T-401 | A1 + A2; A4 review | Tool contract/catalog for existing dry-run tools only | Phase 3 baseline | Complete — contract PR #40 and implementation PR #45 merged |
| T-402 | A2; A4 review | Central registry, validation, deterministic dispatch; no new capability | T-401 | Complete — PR #45 merged; Windows verification passed |
| T-403 | A1 + A2; A4 review | Request-scoped in-memory task lifecycle; no persistence/history | T-401 | Complete — PR #46 merged; 75 backend tests passed |
| T-404 | A3; A4 review | Tool/task status and dry-run UX; Thai default, English option | T-401; T-402/T-403 API | Complete — PR #47 merged; 22 frontend tests passed |
| T-405 | A4 | QA/security matrix and evidence review | T-401; implementation as available | Matrix merged (#44); Windows verification evidence recorded |
| T-406 | A1 + A4 | Integration/documentation closeout recommendation | T-402–T-405 | Complete — Product Owner closeout approved 2026-11-02 |

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
- PR #39 — Phase 4 planning baseline and documentation reconciliation — merged.
- PRs #40–#44 — parallel T-401 through T-405 planning documents — merged.

## Definition of done
A task is complete when approved scope, tests/evidence, A4 review, documentation, and limitations are recorded. Code/runtime PRs require explicit Product Owner merge approval. Phase closeout requires explicit Product Owner approval.
