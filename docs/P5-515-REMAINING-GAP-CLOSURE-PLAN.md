# P5-515 — Remaining Gap Closure Plan

## Purpose and authority

This document tracks the 2 remaining Partial rows in the current P5-515 traceability matrix into bounded work packages. It is a planning and coordination artifact under the Product Owner's existing P5-515 authorization; it does not authorize P2/P3, Phase 6, live PC actions, or a new retention policy.

Runtime changes, if required, must remain within the approved P1 dry-run boundary and use synthetic inputs, fake clocks, in-process clients, and spy handlers. Any code/test PR still requires separate Product Owner merge approval. Documentation-only PRs may be merged under the standing docs-only permission after confirming every changed path is under docs/ and CI passes.

## Current baseline

- Current matrix: 33 Covered / 2 Partial / 0 Not covered or not evidenced. PR #104 is merged and CI-verified; Q30 has browser-emulated viewport evidence but still lacks physical-device and screen-reader results. The Product Owner has accepted the Q35 Static Check limitation; Q35 remains Partial technically. On 2026-11-08 the Product Owner explicitly deferred physical-device and screen-reader testing for Q30 and approved closing P5-515 with Q30 retained as Partial.
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

## Product Owner disposition — Q35

The Product Owner explicitly accepted the limitation that Static Check is not a Runtime Sandbox and directed that this limitation be documented. Keep Q35 as Partial in the technical matrix; do not add a runtime sandbox to P5-515. This is an accepted scope limitation, not proof of sandboxing and not authorization for host inspection or execution.

## Q30 status and Product Owner disposition (2026-11-08)

PR #104 is merged; CI run #42395817656 passed 257 backend tests, Ruff, 36 frontend unit tests, all 9 Playwright E2E tests, and frontend build. The mobile checks are Chromium viewport emulation only. The Product Owner explicitly chose to skip physical iPhone and screen-reader testing for now and directed that P5-515 be closed. Record this as a deferred residual, not a passed test: Q30 remains Partial. Do not expose the app publicly, weaken loopback/authentication, or create a tunnel to obtain evidence.

## Sequencing and gates

1. WP1–WP4: complete and merged; evidence is recorded in the verification report and A4 follow-up review.
2. Q35 disposition is recorded as an accepted limitation; keep its technical status Partial.
3. Q30 physical-device and screen-reader evidence was deferred by the Product Owner on 2026-11-08; retain Partial and do not claim it passed.
4. WP5 final evidence reconciliation and A4 review are complete; the Product Owner explicitly approved P5-515 closeout on 2026-11-08.

All current WP1–WP4 code/test PRs are merged following explicit Product Owner authorization and successful CI/CodeQL. Any future code/test PR still requires a separate explicit Product Owner merge approval.

For each documentation-only PR: verify all changed paths are under docs/ and CI passes; the standing documentation-only merge permission applies.

## Completion forecast

WP1–WP4 are complete. P5-515 is closed by Product Owner approval on 2026-11-08. Q30's physical-device/screen-reader evidence is deferred and remains Partial; Q35's accepted static-check limitation remains Partial technically. No further P5-515 work is open; any future attempt to close either technical gap requires a separately authorized task.

## Safety and exit conditions

- P1 remains dry-run/report only.
- P2/P3 remain denied; no inspection or execution handlers/routes are introduced.
- No Windows host inspection, shell/PowerShell/CMD, process execution, filesystem/registry/network inspection, installer, package manager, live provider, or real machine-changing action.
- No durable audit log, time-based audit retention, chat history, or task history is introduced.
- P5-516 remains separately gated and is not started by this plan.
- P5-515 closeout approved by the Product Owner on 2026-11-08 after A4 final reconciliation. The remaining Partial rows are explicitly dispositioned: Q30 evidence deferred; Q35 static-check limitation accepted. Neither is reclassified as Covered.
