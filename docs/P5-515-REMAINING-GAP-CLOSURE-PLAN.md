# P5-515 — Remaining Gap Closure Plan

## Purpose and authority

This document breaks down the 11 Partial rows in the current P5-515 traceability matrix into bounded work packages. It is a planning and coordination artifact under the Product Owner's existing P5-515 authorization; it does not authorize P2/P3, Phase 6, live PC actions, or a new retention policy.

Runtime changes, if required, must remain within the approved P1 dry-run boundary and use synthetic inputs, fake clocks, in-process clients, and spy handlers. Any code/test PR still requires separate Product Owner merge approval. Documentation-only PRs may be merged under the standing docs-only permission after confirming every changed path is under docs/ and CI passes.

## Current baseline

- Current matrix: 24 Covered / 11 Partial / 0 Not covered or not evidenced.
- Remaining rows: Q02, Q09, Q10, Q11, Q12, Q16, Q25, Q26, Q28, Q30, Q31.
- Approved design baseline: P5-508 decisions and P5-509 reconciliation.
- Relevant binding decisions: backend-owned R0–R3/P0–P3 policy; P1 dry-run only; P2/P3 hard-denied; strict request/model validation; audit option A (ephemeral in-memory events, max 500, oldest-first eviction, cleared on restart); optional diagnostics failure is non-blocking; no durable audit log.

## Work packages

| Package | Matrix rows | Work | Expected change | Estimate |
|---|---|---|---|---|
| WP1 — Request and policy abuse cases | Q02, Q09, Q10, Q11, Q12 | Add focused negative tests for extra fields across request boundaries; malformed/duplicate/inconsistent policy configuration; adversarial model/client attempts to downgrade risk or permission; disabled P2 inspection and P3 execution decisions with spy-handler assertions. Reuse current contracts; do not add P2/P3 routes or execution handlers. | Primarily tests; implementation only if a test exposes a defect against the approved contract. | 1–1.5 days |
| WP2 — Parameter boundaries | Q16 | Add a compact parameter-boundary suite for strict types, forbidden extras, empty/oversized strings, unsupported values, and numeric/order bounds on the existing request/plan models. Cover API rejection before planner/handler where applicable. | Tests; narrowly scoped validation fix only if approved behavior is already explicit. | 0.5–1 day |
| WP3 — Audit failure and retention evidence | Q25, Q26 | Inject a synthetic sink failure and prove optional diagnostics returns safely without fallback or blocking the safe path. Reconcile Q26 against the actual approved retention semantics: 500-event cap, oldest-first eviction, process-local memory, cleared on restart. Do not add time-based expiry or durable storage; neither is part of the approved option A contract. | Tests plus matrix/evidence wording correction; no new retention behavior. | 0.5 day |
| WP4 — Frontend defensive rendering and accessibility | Q28, Q30, Q31 | Test unknown plan/program statuses and missing required response fields; ensure unknown values render a neutral safe state and never imply success. Extend keyboard/focus/accessible-name/live-region checks and responsive small-viewport assertions. Inventory rendered controls across empty, loading, plan, clarification, error, and restored states to prove no approve/execute/install/remove action appears. | Frontend tests; minimal template/CSS fallback fix only if required by the existing UX contract. | 1–1.5 days |
| WP5 — Evidence reconciliation and A4 closeout | All | Run CI on final code/test heads, reconcile each row to exact tests, update verification evidence and Phase 5 status, then perform focused A4 review of the final diff and limitations. Record any item that cannot be closed as a specific PO decision request; do not silently defer it. | Documentation and review evidence. | 0.5–1 day |

Estimates overlap slightly because WP1/WP2 can be developed and reviewed together. Overall target remains approximately 3–5 working days, assuming no newly discovered defect or unresolved Product Owner decision.

## Q26 interpretation — important

The current matrix describes Q26 as “retention cap/expiry/restart” and marks it Partial because time-based expiry is absent. That wording is broader than the approved P5-508/P5-509 decision. The binding decision is ephemeral option A: bounded memory, maximum 500 events, oldest-first eviction, and clear-on-restart. It does not require a time-based event TTL. Existing tests already exercise capacity eviction, the 500-event default, and new-sink/restart emptiness. A4 should verify the exact source/tests and then either:
- mark Q26 Covered with the explicit qualification that time-based expiry is not part of the approved policy; or
- retain Partial only if a required approved behavior is found missing.

Do not implement time-based expiry or durable audit storage without a new explicit Product Owner decision.

## Sequencing and gates

1. WP1 and WP2: backend test-only increments first; review exact changed paths and test intent.
2. WP3: audit failure test and Q26 semantic reconciliation.
3. WP4: frontend test increment; any production UI fix must remain defensive display-only.
4. WP5: final evidence, A4 review, and remaining PO decision list.

For each code/test PR: verify the exact head SHA, all CI jobs, and changed files; then request explicit Product Owner merge approval. Do not merge code/test PRs automatically.

For each documentation-only PR: verify all changed paths are under docs/ and CI passes; the standing documentation-only merge permission applies.

## Completion forecast

Target: 3–5 working days from active execution of this plan. This is an estimate, not a guaranteed completion date. If a test exposes behavior that conflicts with the approved design, stop that work item and present the exact decision needed rather than inventing policy.

## Safety and exit conditions

- P1 remains dry-run/report only.
- P2/P3 remain denied; no inspection or execution handlers/routes are introduced.
- No Windows host inspection, shell/PowerShell/CMD, process execution, filesystem/registry/network inspection, installer, package manager, live provider, or real machine-changing action.
- No durable audit log, time-based audit retention, chat history, or task history is introduced.
- P5-516 remains separately gated and is not started by this plan.
- P5-515 is not complete until remaining rows are supported by evidence or explicitly dispositioned by the Product Owner, A4 review is complete, and the Product Owner explicitly approves P5-515 closeout.
