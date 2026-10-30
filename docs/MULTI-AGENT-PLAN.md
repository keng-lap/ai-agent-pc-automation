# Multi-Agent Development Workflow — Four-Agent Plan

## Current status
Phase 3 closeout was approved by the Product Owner on 2026-10-30. The Product Owner has authorized Phase 4 planning. Phase 4 runtime implementation has not started; see docs/PHASE-4.md.

The Four-Agent process is coordinator-managed with four separated roles. It is not four autonomous LLM processes or a runtime orchestrator. No provider/runtime/credential decisions are made by this workflow.

## Objective
Reduce development time through parallel specialist work while preserving dependencies, source-of-truth documentation, safety boundaries, and Product Owner control.

## Roles
| Agent | Responsibility | Parallel work | Restrictions |
|---|---|---|---|
| A1 — Coordinator / Product Analyst | Requirements, task decomposition, contracts, dependencies, board, integration | Documentation, acceptance criteria, dependency mapping | Cannot change scope, make Product Owner decisions, or merge |
| A2 — Backend Engineer | Python backend contracts, registry, validation, dispatch, tests | Independent backend tasks after contract baseline | Cannot add arbitrary command execution, live provider, or real PC actions without approval |
| A3 — Frontend / UX Engineer | Angular UI, accessibility, Thai/English UX, API integration | UX notes and independent frontend work after API contract | No secrets in browser code; cannot bypass backend authorization |
| A4 — QA / Security Reviewer | Threat model, test strategy, source/diff review, test evidence | Review contracts and prepare test matrix in parallel | Does not approve/merge its own work |

The Product Owner remains final decision-maker. The coordinator is not a privileged agent.

## Operating rules
1. Read project definition, roadmap, active phase document, task reports, and current source before planning.
2. Verify GitHub main and open PRs before creating branches.
3. Break work into bounded tasks with owner, inputs, outputs, acceptance criteria, risk, and dependencies.
4. Parallelize only tasks with independent file ownership and stable contracts.
5. Each implementation task uses its own branch and working directory/worktree.
6. Branch naming for every task, including docs: <type>/<task-id>-<short-name>.
7. Integrate in dependency order, not completion order.
8. Agents submit PRs; they do not merge. Code/runtime PRs require explicit Product Owner merge approval.
9. Documentation/planning may be completed directly when correct, consistent with approved decisions, and within current scope. If it changes a decision, scope, safety boundary, or external data flow, stop and ask.
10. Never claim a test passed unless it was actually run and output inspected.
11. Do not begin dependent work before prerequisites are stable/merged.
12. If requirements conflict, stop and surface the conflict rather than guessing.

## Safety gates
- All PC-changing tools remain dry-run/mock until Phase 5 Safety and Permission System is implemented and explicitly approved.
- No arbitrary shell/PowerShell/command execution; no raw model text passed to a command interpreter.
- No PC inspection or read-only discovery without separate proposal and approval.
- No AI-provider integration, provider sign-in, credentials, live model calls, or external data transfer without explicit decisions.
- Preserve loopback binding and local API authorization.
- Secrets remain server-side and must not enter frontend bundles, logs, PR diffs, or committed files.
- Do not persist chat messages/history or task history.
- No agent may change branch protection, repository permissions, secrets, or CI settings without explicit approval.

## Workflow
Product Owner authorizes scope -> A1 defines contracts/tasks/dependencies -> A2 and A3 analyze independent work -> A4 reviews threat model/test plan -> contract gate -> A2/A3 implement in parallel -> A4 reviews -> A1 checks integration -> Product Owner approves each code merge -> integrate in dependency order and test.

## Phase 4 rollout
See docs/PHASE-4.md for scope, exclusions, T-401 through T-406, dependencies, and acceptance criteria.
| Task | Owner | Deliverable | Status |
|---|---|---|---|
| T-401 | A1 + A2; A4 review | Tool catalog/contract for existing dry-run tools | Planned |
| T-402 | A2; A4 review | Central registry, validation, deterministic dispatch | Planned; depends on T-401 |
| T-403 | A1 + A2; A4 review | Request-scoped in-memory task lifecycle; no persistence | Planned; depends on T-401 |
| T-404 | A3; A4 review | Tool/task status UX, Thai default and English option | Planned; depends on stable API |
| T-405 | A4 | QA/security matrix and evidence review | Planned |
| T-406 | A1 + A4 | Integration and Phase 4 closeout recommendation | Blocked until T-402–T-405 complete |

## Definition of done
- Task scope traces to approved project documentation.
- Branch follows repository convention.
- Changes stay within assigned task and approved phase scope.
- Tests are added/updated and run; unrun checks are marked pending.
- No secrets or unrelated files are included.
- A4 review records correctness, security, tests, and limitations.
- Code/runtime PR has explicit Product Owner merge approval.
- Phase closeout is explicitly approved by Product Owner.

## Open decisions
- Runtime/orchestration framework for four autonomous agents.
- Local processes vs containers vs remote workers.
- Credential and GitHub permission isolation.
- Coordinator implementation approach.
- Token/cost budgets, concurrency, timeouts, retries, and cancellation.

This plan does not select a provider, provision credentials, implement an orchestrator, or authorize real PC automation.
