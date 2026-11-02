# P5-508 — Integrated Phase 5 Design Review and Product Owner Decision Packet

## Status and authority

**Integrated planning packet for Product Owner review. Documentation only.** This packet consolidates P5-501 through P5-507 and identifies decisions required before any runtime implementation can be proposed.

It is not Phase 5 completion, does not approve the individual proposals, and does not authorize runtime implementation, tests, PC inspection, downloads, provider calls, external transfer, installation, removal, or execution.

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

The proposals share a consistent core: backend-owned policy; fixed catalog; strict validation; fail-closed dispatch; no arbitrary commands; no provider; no chat/task history; dry-run only; explicit per-program plan; and no implication that acknowledgement authorizes execution.

**Assessment:** the documentation planning deliverables are drafted, but the design is not yet decision-complete. There are unresolved Product Owner choices, and some contracts must be reconciled after those choices. No runtime work should start merely because this packet exists.

## 2. Document inventory

| Task | Document | Planning status |
|---|---|---|
| P5-501 | `docs/P5-501-THREAT-MODEL.md` | Complete — read-only audit |
| P5-502 | `docs/P5-502-RISK-PERMISSION-PROPOSAL.md` | Proposal drafted; PO review pending |
| P5-503 | `docs/P5-503-CONFIRMATION-CONTRACT.md` | Proposal drafted; PO review pending |
| P5-504 | `docs/P5-504-BACKEND-ENFORCEMENT-ARCHITECTURE.md` | Proposal drafted; PO review pending |
| P5-505 | `docs/P5-505-DRY-RUN-UX-API-CONTRACT.md` | Proposal drafted; PO review pending |
| P5-506 | `docs/P5-506-AUDIT-PRIVACY-RETENTION-PROPOSAL.md` | Proposal drafted; PO review pending |
| P5-507 | `docs/P5-507-QA-SECURITY-MATRIX.md` | Proposal drafted; PO review pending |
| P5-508 | This integrated decision packet | Proposal drafted; PO review pending |

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
- Thai is the default UI language; English is selectable. The exact language choice remains subject to the P5-505 PO decision.
- Audit collection must not become chat/task history. Durable logging is not approved.

This is a target contract, not a claim that the current code already implements this pipeline.

## 4. Reconciliation findings and required clarifications

### 4.1 Risk and permission

P5-502 proposes R0–R3 and P0–P3, with P1 as the only active permission. Confirm the exact mapping for the fixed catalog, and confirm that R2/P2 and R3/P3 are hard-denied with no environment-variable or client override.

### 4.2 Confirmation

P5-503 proposes exact immutable action binding, expiry, one-time use, cancellation, restart invalidation, and concurrency-safe consumption. The proposed 10-minute expiry is a proposal, not an approved value. P5-505 treats acknowledgement as optional. PO must decide whether acknowledgement exists at all in the current P1 workflow.

### 4.3 UX/API

P5-505 proposes illustrative routes and response fields, not a final API. Route design must be reconciled with existing endpoints and P5-504 before implementation. The user-facing report must enumerate every program separately and mark unknown version/source/dependencies/space/impact honestly. No live checks may be implied.

### 4.4 Audit/privacy

P5-506 offers three alternatives: A) bounded ephemeral in-memory events cleared on restart, B) minimal durable local security log, or C) no event collection beyond safe errors. Option B changes the retention boundary and requires explicit approval of duration, size, rotation, access, deletion, and export rules. Recommendation is A or C for the current privacy-minimal P1 stage; no choice is assumed.

### 4.5 Test evidence

P5-507 defines 35 proposed cases. None of these cases has been executed by this planning work. Future claims must include actual commands, exit codes, outputs, commit SHA, environment, fake/spy evidence, and limitations. No test may exercise real machine changes or inspect the user's PC.

## 5. Product Owner decision register

Please decide each item explicitly. "Approve the packet" should not be interpreted as silently resolving all options unless the PO states that intention.

| ID | Decision required | Proposed safe default | Current status |
|---|---|---|---|
| D-P5-01 | Adopt risk classes R0–R3 and backend mapping | Adopt proposal, with R2/R3 denied | Pending |
| D-P5-02 | Adopt permission levels P0–P3 | P1 only active; P2/P3 hard-denied | Pending |
| D-P5-03 | Confirmation expiry | 10 minutes for a review reference | Pending |
| D-P5-04 | Restart and replay behavior | Invalidate pending references on restart; one-time atomic consumption | Pending |
| D-P5-05 | Exact plan binding | Bind to complete immutable per-program plan and parameters; any change invalidates reference | Pending |
| D-P5-06 | P1 acknowledgement | Optional; safest simplest path is show report without acknowledgement unless a clear product need exists | Pending |
| D-P5-07 | UX/API | Thai default, English selectable; approve fields and reconcile routes before implementation | Pending |
| D-P5-08 | Audit collection | A (bounded ephemeral memory cleared on restart) or C (no event collection); do not choose durable B by default | Pending |
| D-P5-09 | Audit schema | Allowlisted metadata only; no prompt, plan body, secrets, raw parameters, or machine inventory | Pending |
| D-P5-10 | Audit failure behavior | Policy evaluation failure denies; optional diagnostics failure must not trigger unsafe fallback | Pending |
| D-P5-11 | Implementation decomposition | Create bounded implementation tasks only after decisions are resolved and contracts reconciled | Pending |
| D-P5-12 | Phase 5 runtime start | Require a separate explicit PO instruction after planning approval | Not authorized |

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

The Product Owner may approve, revise, or defer each decision in Section 5. Until explicit decisions are recorded:
- All P5-502 through P5-507 proposals remain pending review.
- No runtime implementation may begin.
- P1 dry-run/mock remains the only permitted mode.
- P2/P3 and Phase 6 remain disabled/not authorized.

