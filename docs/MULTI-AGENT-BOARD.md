# Four-Agent Rollout Board

## Purpose and operating mode

This board tracks the first controlled rollout of the four-agent development workflow described in `MULTI-AGENT-PLAN.md`.

**Important:** this rollout is a coordinator-managed workflow simulation using four clearly separated roles. It does not claim that four autonomous LLM processes or a runtime orchestrator have been launched. Runtime/provider/credential decisions remain open.

## Current baseline

- Repository: `keng-lap/ai-agent-pc-automation`
- Baseline branch: `main`
- Baseline commit: `b2b029bc11e5d3ac7d9a91f8c28321d4ad5851b8`
- Phase 3: verification evidence recorded; T-307 automated regression and final rerun remain pending.
- Phase 4: not started.
- All PC-changing operations remain mock/dry-run only.
- No live AI provider calls, provider sign-in, or external data transfer are authorized.

## Role assignments

| Role | Responsibility | Current assignment | Status |
|---|---|---|---|
| A1 — Coordinator / Product Analyst | Own task decomposition, dependencies, integration sequence, and board | MA-001 inventory and rollout coordination | In progress |
| A2 — Backend Engineer | Own backend test/code task on an isolated branch | T-307 duplicate-token regression test | Branch created; PR pending |
| A3 — Frontend / UX Engineer | Own frontend verification evidence and browser-boundary review | Production build and token-leak scan | Evidence passed; recorded in T-306 report branch |
| A4 — QA / Security Reviewer | Independently review acceptance criteria, security boundary, and evidence | Review T-307 test design and T-306 evidence | Pending review |

## Task board

| ID | Owner | Scope | Dependency | Branch | Status |
|---|---|---|---|---|---|
| MA-001 | A1 + A4 | Inventory current phase, repository baseline, safety rules, and acceptance gates | None | `docs/MA-001-four-agent-rollout` | In progress |
| MA-002 | A1 | Maintain this role/task board and dependency map | MA-001 | Same documentation branch | In progress |
| T-307 | A2 | Add automated regression test for duplicate local-token headers; no runtime behavior change | T-306 merged | `test/T-307-duplicate-token-regression` | Branch created; PR pending |
| MA-003 | A3 + A4 | Record Windows 11 verification and review production bundle/token boundary | T-306 merged | `docs/T-306-verification-record` | Documentation branch prepared |
| MA-004 | A1–A4 | Dry-run one bounded task through all four roles; no runtime orchestration or PC actions | MA-001 through MA-003 | To be assigned after review | Not started |

## Dependency map

```text
MA-001 repository and safety inventory
       |
       +------> T-307 backend regression test (A2)
       |
       +------> MA-003 verification evidence (A3)
                         |
                         v
                  A4 QA/security review
                         |
                         v
                  A1 integration report
                         |
                         v
              Product Owner review / approval
```

T-307 and documentation work may proceed independently because they own different files and branches. Final Phase 3 closure depends on T-307 being merged and the complete test suite being rerun.

## Branch and approval controls

- Every task uses `<type>/<task-id>-<short-name>`.
- Each task owns a separate branch; no shared working tree writes.
- Agents do not merge PRs.
- Product Owner approval is required for every merge.
- No branch protection, repository permission, CI setting, secret, provider, or safety-boundary changes are included.
- Any change to approved decisions or phase scope stops for Product Owner approval.

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
