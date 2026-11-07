# P5-508 — Integrated Phase 5 Design Review and Product Owner Decision Packet

## Status and authority

**Product Owner decisions recorded — all 12 decisions approved on 2026-10-30. Documentation only.** This packet consolidates P5-501 through P5-507 and records the approved design baseline.

It is not Phase 5 completion or approval of runtime implementation. It records the approved design decisions, but does not authorize tests, PC inspection, downloads, provider calls, external transfer, installation, removal, or execution.

Current permission remains P1 — dry-run / plan and report only. P2 inspection and P3 machine-changing execution remain disabled. Phase 6 is not authorized. Existing `software.install` and `software.remove` tools remain dry-run/mock only.

## 1. Executive assessment

The planning set now covers:
- Threat model and existing security boundary (P5-501).
- Risk and permission classification (P5-502).
- Confirmation lifecycle and exact-action binding (P5-503).
- Backend policy enforcement architecture (P5-504).
- Thai-default bilingual dry-run UX/API (P5-505).
- Audit event, privacy, retention, and access (P5-506).
- QA/security matrix and evidence plan (P5-507).

The approved design baseline is: backend-owned policy; fixed catalog; strict validation; fail-closed dispatch; no arbitrary commands; no provider; no chat/task history; dry-run only; explicit per-program plan; and no implication that acknowledgement authorizes execution.

**Assessment:** all 12 Product Owner design decisions are approved and recorded below. Contract reconciliation and bounded implementation-task decomposition may proceed as documentation/planning work. Runtime implementation is still NOT authorized; a separate explicit Product Owner instruction is required.

## 2. Document inventory

| Task | Document | Planning status |
|---|---|---|
| P5-501 | `docs/P5-501-THREAT-MODEL.md` | Complete — read-only audit |
| P5-502 | `docs/P5-502-RISK-PERMISSION-PROPOSAL.md` | Proposal drafted; PO decision approved |
| P5-503 | `docs/P5-503-CONFIRMATION-CONTRACT.md` | Proposal drafted; PO decision approved |
| P5-504 | `docs/P5-504-BACKEND-ENFORCEMENT-ARCHITECTURE.md` | Proposal drafted; PO decision approved |
| P5-505 | `docs/P5-505-DRY-RUN-UX-API-CONTRACT.md` | Proposal drafted; PO decision approved |
| P5-506 | `docs/P5-506-AUDIT-PRIVACY-RETENTION-PROPOSAL.md` | Proposal drafted; PO decision approved |
| P5-507 | `docs/P5-507-QA-SECURITY-MATRIX.md` | Proposal drafted; PO decision approved |
| P5-508 | This integrated decision packet | Approved design baseline |

## 3. Integrated target architecture

The proposed future P1-only path is:

`HTTP boundary → strict request validation → fixed catalog/intent resolution → backend risk and permission derivation → policy decision → final pre-dispatch guard → side-effect-free dry-run handler → strict result validation → plan/report presentation`

Cross-cutting constraints:
- No client/model-provided risk, permission, approval, handler identity, execution mode, or policy version is trusted.
- No arbitrary shell, PowerShell, CMD, script, process, dynamic import, package manager, installer, filesystem/registry operation, network lookup, or machine inspection.
- Policy failure, invalid parameters, unknown tool, handler mismatch, and unverifiable state deny before dispatch.
- A P1 acknowledgement, if approved, is only an acknowledgement of a specific displayed dry-run plan. It is not identity proof or execution consent.
- A changed plan invalidates the prior review reference.
- No execute/install/remove endpoint or UI control exists in P1.
- Thai is the default UI language; English is selectable.
- Audit collection must not become chat/task history. Durable logging is not approved.

This is a target contract, not a claim that the current code already implements this pipeline.

## 4. Reconciliation findings and required clarifications

### 4.1 Risk and permission

Approved: adopt R0–R3 and P0–P3; P1 is the only active permission. R2/R3 and P2/P3 are hard-denied, with no client or environment-variable override.

### 4.2 Confirmation

P5-503 proposes exact immutable action binding, expiry, one-time use, cancellation, restart invalidation, and concurrency-safe consumption. Approved: 10-minute expiry for any review reference. P5-505 treats acknowledgement as optional. Approved: no acknowledgement step is required in the current P1 workflow; displaying the dry-run report is sufficient. If an acknowledgement is later proposed, it remains informational only and requires a separately reviewed change.

### 4.3 UX/API

P5-505 proposes illustrative routes and response fields, not a final API. Route design must be reconciled with existing endpoints and P5-504 before implementation. The user-facing report must enumerate every program separately and mark unknown version/source/dependencies/space/impact honestly. No live checks may be implied.

### 4.4 Audit/privacy

P5-506 offers three alternatives: A) bounded ephemeral in-memory events cleared on restart, B) minimal durable local security log, or C) no event collection beyond safe errors. Option B changes the retention boundary and requires explicit approval of duration, size, rotation, access, deletion, and export rules. Approved: option A — bounded ephemeral in-memory events cleared on restart. Durable logging (option B) is not approved.

### 4.5 Test evidence

P5-507 defines 35 proposed cases. None of these cases has been executed by this planning work. Future claims must include actual commands, exit codes, outputs, commit SHA, environment, fake/spy evidence, and limitations. No test may exercise real machine changes or inspect the user's PC.

## 5. Product Owner decision register

The Product Owner explicitly approved all 12 decisions on 2026-10-30, using the proposed safe defaults. The table records the binding decisions:

| ID | Decision | Approved decision / status | Status |
|---|---|---|---|
| D-P5-01 | Adopt risk classes R0–R3 and backend mapping | Approved — adopt proposal; R2/R3 denied | Approved |
| D-P5-02 | Adopt permission levels P0–P3 | Approved — P1 only active; P2/P3 hard-denied | Approved |
| D-P5-03 | Confirmation expiry | Approved — 10 minutes for a review reference | Approved |
| D-P5-04 | Restart and replay behavior | Approved — invalidate pending references on restart; one-time atomic consumption | Approved |
| D-P5-05 | Exact plan binding | Approved — bind complete immutable per-program plan and parameters; any change invalidates reference | Approved |
| D-P5-06 | P1 acknowledgement | Approved — no acknowledgement required for current P1 report; any future acknowledgement is informational only | Approved |
| D-P5-07 | UX/API | Approved — Thai default, English selectable; reconcile API routes/contracts before implementation | Approved |
| D-P5-08 | Audit collection | Approved — A: bounded ephemeral in-memory events cleared on restart; durable B is not approved | Approved |
| D-P5-09 | Audit schema | Approved — allowlisted metadata only; no prompt, plan body, secrets, raw parameters, or machine inventory | Approved |
| D-P5-10 | Audit failure behavior | Approved — policy evaluation failure denies; diagnostics failure never triggers unsafe fallback | Approved |
| D-P5-11 | Implementation decomposition | Approved — create bounded implementation tasks after contracts are reconciled | Approved |
| D-P5-12 | Phase 5 runtime start | Not authorized — separate explicit PO instruction still required | Not authorized |

## 6. Recommended implementation sequencing — not authorized

If and only if the PO approves the relevant decisions and separately authorizes runtime work, the proposed order is:

1. **I1 — Static policy and startup validation:** immutable policy table, schema consistency checks, and hard denial for disabled permissions.
2. **I2 — Policy decision point and final dispatch guard:** backend derivation, decision outcomes, final recheck, no fallback, spy-handler negative tests.
3. **I3 — P1 plan/report contract:** exact per-program plan model and dry-run result; no execute path.
4. **I4 — Confirmation/review lifecycle:** only if P1 acknowledgement is approved; exact digest binding, expiry, cancellation, replay/concurrency behavior; informational only.
5. **I5 — Audit/privacy implementation:** only after event collection and retention choice are explicitly approved.
6. **I6 — Frontend UX/API integration:** Thai-default bilingual display, explicit unknowns, accessibility, no execution control.
7. **I7 — Full negative/abuse/regression verification and independent A4 review.**

Dependencies must be revisited after decisions. This list does not start any task. Runtime branches and PRs require separate PO authorization and explicit code-merge approval.

## 7. Phase 5 exit criteria

Phase 5 cannot be marked complete until:
- All relevant PO decisions are explicit or explicitly deferred with documented impact.
- P5-502 through P5-506 are reconciled into one consistent approved design.
- Any authorized runtime implementation is bounded, reviewed, and mock/dry-run only.
- QA/security cases have real recorded evidence; planning documents alone do not satisfy test criteria.
- A4 independent review is complete.
- No real execution capability has been introduced.
- Product Owner explicitly approves Phase 5 closeout.

Even after Phase 5 closeout, Phase 6 and each individual capability require separate authorization. No automatic transition to real execution is permitted.

## 8. Work performed and limitations

This packet is based on the planning documents in GitHub main. The planning work did not run code, tests, linters, CI, machine inspection, penetration tests, package/source checks, or any PC operation. It does not claim that current runtime code satisfies the proposed target architecture.

## 9. Product Owner response

The Product Owner has approved the decisions in Section 5. P5-502 through P5-507 must be reconciled to this baseline. Bounded task decomposition is permitted as planning work. No runtime implementation may begin until a separate explicit PO instruction. P1 dry-run/mock remains the only permitted mode; P2/P3 and Phase 6 remain disabled/not authorized.


## 10. Approval record

On 2026-10-30, the Product Owner explicitly confirmed: “ทั้ง 12 ข้อเลย” — approving all 12 decisions using the recommended safe defaults. This approval resolves D-P5-01 through D-P5-11 as recorded above. D-P5-12 remains a separate gate: runtime implementation has not been authorized.


## 11. Superseding Product Owner decision — 2026-11-07

The Product Owner subsequently directed: “เพิ่ม apporve แล้วค่อย dry รัน” (add approval first, then dry run). This is a new, explicit decision that supersedes the earlier D-P5-06 rule for the current P1 workflow. The 2026-10-30 decision remains in the historical register above; it is not silently rewritten.

**D-P5-13 — P1 approval gate before Dry Run: Approved on 2026-11-07.**

- The user must see the exact immutable per-program plan before any dry-run handler is called.
- Dry Run is permitted only after an explicit user action on the approval control for that exact plan.
- Approval is backend-owned, bound to the server-created plan ID and digest, and subject to the existing 10-minute plan expiry and process-restart invalidation.
- Every program marked `PLANNED` in the approved plan must receive its own fixed dry-run handler invocation. The result must account for every listed program; a partial simulation must not be presented as a complete plan result.
- A plan with any `NEEDS_CLARIFICATION`, `BLOCKED`, or `UNSUPPORTED` item cannot be approved. Refinement creates a new plan and requires a new approval.
- Repeated approval requests may return the cached result but must not dispatch handlers again.
- Approval authorizes **P1 Dry Run only**. It does not authorize installation, removal, OS inspection, shell/process execution, downloads, package-manager access, or any Windows change.
- No acknowledgement, cancel, execute, install, or remove endpoint/control is introduced. The sole state-changing P1 route is `POST /api/plans/{plan_id}/approve`.
- The approval control must clearly say “อนุมัติให้จำลอง (Dry Run)” (or equivalent) and the result must state “จำลองเท่านั้น — ไม่มีการเปลี่ยนแปลงใด ๆ กับเครื่อง”.

**Bounded runtime task authorization:** The Product Owner authorized P5-517 on 2026-11-07 to reconcile the approval-gated P1 workflow, correct per-program Dry Run coverage, update the related tests and documentation, and provide a testable PR. This does not authorize merging the runtime PR, Phase 6, or any real PC-changing action. Product Owner review is required before merge.
