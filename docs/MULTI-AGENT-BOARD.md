# Four-Agent Rollout Board

## Purpose and operating mode

This board tracks the controlled rollout of the four-agent development workflow described in `MULTI-AGENT-PLAN.md`.

**Operating-mode clarification:** this is currently a coordinator-managed workflow simulation with four separated responsibilities. It is not four autonomous LLM processes, and no runtime multi-agent orchestrator has been implemented. Provider/runtime/credential decisions remain open.

## Current repository baseline

- Repository: `keng-lap/ai-agent-pc-automation`
- Default branch: `main`
- Baseline commit before this documentation follow-up: `e6d6a83b51b5b49e23db0fc592fcf35abaa83766`
- Baseline date: 2026-10-30 (after PR #36 merge)
- PRs #30 (T-307), #31 (T-306 verification docs), #32 (MA-001 rollout docs), #33 (MA-005 board/Phase 3 QA audit), #35 (T-308 implementation), and #36 (T-308 parser fix) are merged.
- T-306 and T-307 verification evidence is recorded in `docs/T-306-REPORT.md`.
- Phase 3 closeout is **not approved**. T-308 implementation PR #35 and parser correction PR #36 are merged. The latest Product Owner Windows 11 test-script run passed (100 backend tests, Ruff, 21 frontend tests). A4's independent final acceptance reassessment remains pending. See `docs/PHASE-3-QA-REVIEW.md` and `docs/T-308-REPORT.md`.
- Phase 4: not started.
- All PC-changing operations remain mock/dry-run only.
- No live AI provider calls, provider sign-in, or external data transfer are authorized.

## Role assignments

| Role | Responsibility | Current assignment | Status |
|---|---|---|---|
| A1 — Coordinator / Product Analyst | Own task decomposition, dependencies, integration sequence, and board | T-308 post-merge documentation reconciliation | PRs #35/#36 merged; this documentation follow-up in progress |
| A2 — Backend Engineer | Own backend task on an isolated branch | T-308 task-specific prerequisite planning and parser correction | PRs #35/#36 merged; Windows test evidence recorded |
| A3 — Frontend / UX Engineer | Own frontend verification and browser-boundary evidence | T-306 production build, proxy, and token-leak verification | Complete; evidence recorded in PR #31 |
| A4 — QA / Security Reviewer | Independently review acceptance criteria, security boundary, and evidence | Final independent Phase 3 acceptance reassessment | In progress; must assess all criteria and record any remaining gaps |

## Task board

| ID | Owner | Scope | Dependency | Branch / PR | Status |
|---|---|---|---|---|---|
| MA-001 | A1 + A4 | Inventory repository, phase status, safety rules, and acceptance gates | None | PR #32 | Complete; merged |
| MA-002 | A1 | Maintain role/task board and dependency map | MA-001 | PR #32; maintained by MA-005 | Complete; merged |
| T-307 | A2 | Add automated duplicate local-token header regression test | T-306 merged | PR #30 | Complete; merged; final Windows test rerun passed |
| MA-003 | A3 + A4 | Record Windows 11 verification and review browser/token boundary | T-306 merged | PR #31 | Complete; merged |
| MA-004 | A1–A4 | Dry-run one bounded documentation task through four roles; no runtime orchestration or PC actions | MA-001–MA-003 | Not assigned | Not started |
| MA-005 | A1 + A4 | Reconcile board/plan with merged GitHub state and audit Phase 3 acceptance criteria | PRs #30–#32 merged | PR #33 | Complete; merged into main (`af3006b`) |\n| T-308 | A2 + A4 | Add task-specific prerequisite items, reasons, dependency order, and explicit knowledge states | MA-005 finding; scope approved by Product Owner | PR #35; parser fix PR #36 | Complete; both PRs merged; latest Windows 11 test script passed; final A4 acceptance reassessment pending |

## Dependency map

```text
MA-001 repository and safety inventory (merged)
       |
       +------> T-307 backend regression test (merged)
       |
       +------> MA-003 Windows verification evidence (merged)
                         |
                         v
                  MA-005 A4 acceptance review
                         |
             +-----------+------------+
             |                        |
       Evidence passes          Acceptance gap
       recorded                 task required
             |                        |
             +-----------+------------+
                         |
                 A1 integration report
                         |
                 Product Owner review
```

MA-005 identified a Phase 3 planning gap. T-308 now proposes structured category-specific prerequisites with reasons, dependency references, and explicit `known` / `user_confirmation_needed` / `discovery_not_available` states. The implementation and parser fix are merged in PRs #35 and #36. The latest Windows 11 test-script run passed (100 backend tests, Ruff, 21 frontend tests). It does not inspect the PC or browse sources; those facts remain marked unavailable. Do not close Phase 3 until A4 completes its independent acceptance reassessment and the Product Owner approves closeout.

## Branch and approval controls

- Every task uses `<type>/<task-id>-<short-name>`.
- Each task owns a separate branch; no shared working-tree writes.
- Agents do not merge PRs.
- Product Owner approval is required for every merge.
- No branch protection, repository permission, CI setting, secret, provider, or safety-boundary changes are included.
- Any change to approved decisions or phase scope stops for Product Owner approval.
- The current default branch is not protected by required status checks; MA-005 does not change repository settings.

## Definition of done

- Scope traces to an approved project document.
- Dependencies and acceptance criteria are explicit.
- Changes are isolated to the assigned task.
- Tests are run and evidence is recorded; unrun checks remain pending.
- No secrets are committed or exposed in logs/bundles.
- PR includes summary, test evidence, limitations, and safety impact.
- Product Owner explicitly approves merge.

## Open decisions — not selected by this rollout

- Runtime/orchestration framework for four autonomous agents.
- Local processes vs containers vs remote workers.
- Credential and GitHub permission isolation.
- Coordinator implementation (deterministic code or LLM-backed).
- Token/cost budgets, concurrency, timeouts, retries, and cancellation.

This board does not authorize implementing an agent orchestrator, connecting a provider, or enabling real PC automation.

## Merged rollout pull requests

- [PR #30 — T-307 duplicate-token regression test](https://github.com/keng-lap/ai-agent-pc-automation/pull/30) — merged; merge commit `7b12e92edaa4ffdd91946c27af6573c0fe68d69a`.
- [PR #31 — T-306 verification evidence](https://github.com/keng-lap/ai-agent-pc-automation/pull/31) — merged; merge commit `0aea6b77bef55f07e32611c814781ef575c0c065`.
- [PR #32 — MA-001 four-agent rollout board](https://github.com/keng-lap/ai-agent-pc-automation/pull/32) — merged; merge commit `a39e6052f3e5be0509547c70ec61ade2ac69ba24`.\n- [PR #33 — MA-005 board reconciliation and Phase 3 QA audit](https://github.com/keng-lap/ai-agent-pc-automation/pull/33) — merged; merge commit `af3006b508fea70e1e15174f54e2a2ca3da82edc`.\n- [PR #35 — T-308 task-specific prerequisite planning](https://github.com/keng-lap/ai-agent-pc-automation/pull/35) — merged.\n- [PR #36 — T-308 polite install request parser fix](https://github.com/keng-lap/ai-agent-pc-automation/pull/36) — merged; merge commit `e6d6a83b51b5b49e23db0fc592fcf35abaa83766`.

All listed PRs are merged into `main`. This documentation follow-up does not authorize any merge.
