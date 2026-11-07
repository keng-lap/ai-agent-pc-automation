# P5-515 — Remaining Gap Closure Plan

## Purpose and authority

This document tracks the 2 remaining Partial rows in the current P5-515 traceability matrix into bounded work packages. It is a planning and coordination artifact under the Product Owner's existing P5-515 authorization; it does not authorize P2/P3, Phase 6, live PC actions, or a new retention policy.

Runtime changes, if required, must remain within the approved P1 dry-run boundary and use synthetic inputs, fake clocks, in-process clients, and spy handlers. Any code/test PR still requires separate Product Owner merge approval. Documentation-only PRs may be merged under the standing docs-only permission after confirming every changed path is under docs/ and CI passes.

## Current baseline

- Current matrix: 33 Covered / 2 Partial / 0 Not covered or not evidenced.
- Remaining rows: Q30 and Q35.
- WP1–WP4 are complete and merged: PRs #85, #81, #82, and #84. Original PR #80 was closed as superseded after its branch diverged; WP1 was reapplied on current main in PR #85.
- Approved design baseline: P5-508 decisions and P5-509 reconciliation.
- Relevant binding decisions: backend-owned R0–R3/P0–P3 policy; P1 dry-run only; P2/P3 hard-denied; strict request/model validation; audit option A (ephemeral in-memory events, max 500, oldest-first eviction, cleared on restart); optional diagnostics failure is non-blocking; no durable audit log.

## Work packages

| Package | Matrix rows | Work | Expected change | Estimate |
|---|---|---|---|---|
| WP1 — Request and policy abuse cases | Q02, Q09, Q10, Q11, Q12 | Add focused negative tests for extra fields across request boundaries; malformed/duplicate/inconsistent policy configuration; adversarial model/client attempts to downgrade risk or permission; disabled P2 inspection and P3 execution decisions with spy-handler assertions. Reuse current contracts; do not add P2/P3 routes or execution handlers. | Primarily tests; implementation only if a test exposes a defect against the approved contract. | 1–1.5 days |
| WP2 — Parameter boundaries | Q16 | Add a compact parameter-boundary suite for strict types, forbidden extras, empty/oversized strings, unsupported values, and numeric/order bounds on the existing request/plan models. Cover API rejection before planner/handler where applicable. | Tests; narrowly scoped validation fix only if approved behavior is already explicit. | 0.5–1 day |
| WP3 — Audit failure evidence | Q25 | Inject a synthetic sink failure and prove optional diagnostics returns safely without fallback or blocking the safe path. Q26 is now Covered by existing tests and reconciled documentation against approved option A retention semantics. | Test for Q25; documentation reconciliation for Q26. | 0.5 day |
| WP4 — Frontend defensive rendering and accessibility | Q28, Q30, Q31 | Test unknown plan/program statuses and missing required response fields; ensure unknown values render a neutral safe state and never imply success. Extend keyboard/focus/accessible-name/live-region checks and responsive small-viewport assertions. Inventory rendered controls across empty, loading, plan, clarification, error, and restored states to prove no approve/execute/install/remove action appears. | Frontend tests; minimal template/CSS fallback fix only if required by the existing UX contract. | 1–1.5 days |
| WP5 — Evidence reconciliation and A4 closeout | All | Run CI on final code/test heads, reconcile each row to exact tests, update verification evidence and Phase 5 status, then perform focused A4 review of the final diff and limitations. Record any item that cannot be closed as a specific PO decision request; do not silently defer it. | Documentation and review evidence. | 0.5–1 day |

Estimates overlap slightly because WP1/WP2 can be developed and reviewed together. Overall target remains approximately 3–5 working days, assuming no newly discovered defect or unresolved Product Owner decision.

## Q26 disposition

Q26 is Covered after A4 reconciled the matrix with the approved P5-508 option A semantics: bounded in-memory events, maximum 500, oldest-first eviction, and clear-on-restart. The existing audit tests directly cover capacity, FIFO eviction, and new-sink emptiness. Time-based event expiry and durable audit storage are not required or authorized; no TTL or durable persistence was added.

## Sequencing and gates

1. WP1–WP4: complete and merged; evidence is recorded in the verification report and A4 follow-up review.
2. WP5: complete the final evidence reconciliation and A4 review; obtain Product Owner disposition for Q30 and Q35, then explicit P5-515 closeout approval.

All current WP1–WP4 code/test PRs are merged following explicit Product Owner authorization and successful CI/CodeQL. Any future code/test PR still requires a separate explicit Product Owner merge approval.

For each documentation-only PR: verify all changed paths are under docs/ and CI passes; the standing documentation-only merge permission applies.

## Completion forecast

WP1–WP4 are complete. Remaining effort is limited to Q30 browser-level mobile/accessibility evidence, Q35 capability-boundary disposition, and final Product Owner closeout. If evidence cannot be obtained within the authorized scope, present the exact residual limitation for explicit disposition rather than inventing policy.

## Safety and exit conditions

- P1 remains dry-run/report only.
- P2/P3 remain denied; no inspection or execution handlers/routes are introduced.
- No Windows host inspection, shell/PowerShell/CMD, process execution, filesystem/registry/network inspection, installer, package manager, live provider, or real machine-changing action.
- No durable audit log, time-based audit retention, chat history, or task history is introduced.
- P5-516 remains separately gated and is not started by this plan.
- P5-515 is not complete until remaining rows are supported by evidence or explicitly dispositioned by the Product Owner, A4 review is complete, and the Product Owner explicitly approves P5-515 closeout.
