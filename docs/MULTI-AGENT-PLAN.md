# Multi-Agent Development Workflow — Four-Agent Plan

## Status

**Controlled workflow definition and initial documentation rollout are merged.** The current implementation is a coordinator-managed workflow simulation with four separated roles, not four autonomous LLM processes or a runtime orchestrator. No runtime multi-agent system, provider connection, credentials, or real PC execution is authorized.

The current `main` baseline is `af3006b508fea70e1e15174f54e2a2ca3da82edc` (2026-10-30). PRs #30, #31, #32, and #33 are merged.

## Objective

Use four specialized roles to reduce development time while preserving the Product Owner's control, repository safety, phase order, and review quality.

## Four roles

| Agent | Responsibility | Allowed parallel work | Must not do |
|---|---|---|---|
| A1 — Coordinator / Product Analyst | Read source-of-truth docs, split approved work into bounded tasks, map dependencies, maintain task board and integration plan | Requirements analysis, acceptance criteria, dependency mapping, progress summaries | Change scope, approve decisions, merge PRs |
| A2 — Backend Engineer | Backend contracts, API, deterministic Agent logic, backend tests | Independent backend task on its own branch | Bypass allowlists, enable live provider or machine-changing execution without approval |
| A3 — Frontend / UX Engineer | Angular UI, accessibility, Thai/English UX, API integration | Independent frontend task on its own branch | Put secrets in browser code or bypass backend authorization |
| A4 — QA / Security Reviewer | Test strategy, threat modelling, test execution, diff review, regression checks | Review completed or stable changes; prepare tests and findings | Modify another agent's branch without an assigned fix task; approve/merge its own work |

The coordinator is a workflow role, not a privileged agent. The Product Owner remains the final decision-maker.

## Parallel execution rules

1. Start by reading `README.md`, `docs/PROJECT.md`, `docs/ROADMAP.md`, the active phase document, and relevant task reports.
2. Confirm the current phase and its approved scope before creating tasks.
3. Break work into small tasks with explicit inputs, outputs, acceptance criteria, risk, and dependencies.
4. Run parallel tasks only when their dependency sets do not overlap in a way that requires shared edits.
5. Each implementation agent uses a separate branch and working directory/worktree. Never have two agents write to the same branch or shared working tree.
6. Branch convention for every task, including docs: `<type>/<task-id>-<short-name>`.
7. Agents submit PRs; they do not merge. The coordinator checks completeness and reports conflicts. The Product Owner reviews and explicitly approves every merge.
8. If a task changes an approved decision, security boundary, data flow, provider, permission, or phase scope, stop and request Product Owner approval before implementation.
9. Never claim tests passed unless the command was actually run and its output was inspected. Record exact commands, environment, and results.
10. Do not start dependent tasks until their prerequisites are merged and verified.

## Safety gates

- All PC-changing tools remain mock/dry-run until the approved Safety and Permission System phase is implemented and explicitly approved.
- No raw model output may be executed as a shell command.
- No AI-provider integration, provider sign-in, external data transfer, or live model calls without explicit Product Owner decisions.
- Local API authorization must remain enforced. Secrets stay server-side and must never enter frontend bundles, logs, PR diffs, or committed files.
- Agents receive only the minimum repository/tool permissions needed for their task.
- No agent may change branch protection, repository permissions, secrets, or CI settings without explicit approval.

## Task lifecycle

```text
Product Owner approves scope
        |
        v
A1 decomposes work and dependencies
        |
        v
A2 / A3 implement independent tasks in parallel
        |
        v
A4 reviews tests, security, and regressions
        |
        v
A1 checks integration readiness and reports
        |
        v
Product Owner reviews and approves each merge
        |
        v
Merge one PR at a time, then run integration checks
```

## Dependency and conflict policy

- One task owns one set of files wherever practical.
- If two tasks need the same contract or file, A1 must sequence them or create a prior contract task.
- API/schema changes are agreed before frontend implementation depends on them.
- A4 may prepare tests in parallel only against an approved contract; otherwise it records test proposals rather than guessing behavior.
- Integrate in dependency order, not in the order PRs happen to finish.
- A failed check returns to the owning agent as a bounded fix task. Do not silently patch another agent's work.

## Initial rollout — documentation-only status

| Step | Owner | Deliverable | Current status |
|---|---|---|---|
| MA-001 | A1 + A4 | Inventory repository, phase status, branch/PR conventions, safety constraints | Complete; PR #32 merged |
| MA-002 | A1 | Task decomposition template, dependency map, four-agent responsibility matrix | Complete; PR #32 merged and board maintained in MA-005 |
| MA-003 | A4 | Definition of done and verification evidence review | T-306/T-307 evidence recorded in PR #31; MA-005 performed Phase 3 acceptance review |
| MA-004 | A1–A4 | Dry-run simulation of one small documentation-only task across all four roles | Not started; separate approval/scope required |
| MA-005 | A1 + A4 | Reconcile merged GitHub state and audit Phase 3 acceptance criteria | Complete; PR #33 merged; see `docs/PHASE-3-QA-REVIEW.md` |\n| T-308 | A2 + A4 | Add structured task-specific prerequisites and deterministic tests | Implementation submitted in Draft PR #35; tests and final A4 acceptance pending |

## Current project gate

T-306 and T-307 are merged and their Windows 11 verification is recorded in `docs/T-306-REPORT.md`. The final Product Owner test-script rerun after T-307 passed (backend 100 tests, Ruff, frontend 21 tests).

However, A4's MA-005 review found that the planner did not identify task-specific prerequisites or justify them. T-308 now has an implementation candidate in Draft PR #35: structured prerequisite items with reasons, dependency order, and explicit knowledge states. No local inspection or web research is claimed. Tests, Windows verification, and A4's final acceptance reassessment remain pending. Phase 3 closeout remains blocked; Phase 4 must not start before explicit Product Owner approval.

## Definition of done for an agent task

- Task scope and acceptance criteria trace to an approved project document.
- Branch follows the repository convention.
- Changes are limited to the assigned task.
- Tests/checks are run where feasible; unavailable checks are explicitly marked pending.
- No secrets or unrelated files are included.
- PR description includes summary, evidence, limitations, and safety impact.
- Product Owner has explicitly approved the merge.

## Open decisions

- Which orchestration runtime will host the four development agents.
- Whether agents will be local processes, containers, or remote workers.
- How credentials and GitHub permissions will be isolated.
- Whether the coordinator is deterministic code or an LLM-backed agent.
- Token/cost budgets, concurrency limits, timeout, retry, and cancellation policy.

These decisions remain open. This document does not select a provider or authorize credential provisioning.
