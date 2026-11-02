# P5-503 — Confirmation Lifecycle and Exact-Action Binding Contract

## Status

**Proposal for Product Owner review. Documentation only.** This contract does not authorize runtime implementation, machine inspection, installation, removal, downloads, or execution.

Depends on P5-502. The active project boundary remains P1 — Dry-run / plan and report only. This document designs a safe lifecycle and records how a future separately approved capability would bind consent to one exact action. It does not activate that capability.

## 1. Governing principles

1. The backend is the sole authority for action validation, risk classification, permission checks, and confirmation state.
2. The model, planner, browser UI, client request, and local API token cannot approve an action or raise a permission level.
3. A confirmation must refer to one immutable, backend-validated action payload. It is never a blanket approval for a tool, program category, session, or future request.
4. Any change to the action identity or any parameter invalidates the prior confirmation.
5. Missing, malformed, expired, consumed, revoked, mismatched, or unverifiable confirmation state fails closed.
6. Confirmation is not execution permission. Current P1 confirmation can only acknowledge/review a dry-run plan; it cannot authorize machine access or state change.
7. No chat content or task history is persisted as part of this design.

## 2. Separate plan review from authorization

The UI and API must distinguish two different concepts:

- **Plan review acknowledgement (current P1):** the user has reviewed a specific proposed installation list and dry-run report. This acknowledgement has no machine authority and must not be represented as permission to install.
- **Execution authorization (not enabled):** a future capability that could authorize one exact action only after separate Product Owner approval, Phase 5 completion, Phase 6 authorization for that capability, and a reviewed backend enforcement design.

Do not label a P1 button "Approve and execute", "Install", or equivalent. If a review acknowledgement is implemented later, use wording such as "รับทราบแผน (Dry-run เท่านั้น) / Acknowledge plan (dry-run only)".

## 3. Exact action representation

The backend should construct a canonical, typed action envelope from the fixed tool catalog and validated request. The client/model must not supply trusted risk, permission, handler, or authorization fields.

Proposed envelope fields:

| Field | Meaning |
|---|---|
| `action_id` | Server-generated opaque identifier for this one action |
| `tool_id` | Exact fixed catalog tool identifier |
| `tool_version` | Version of the tool contract/schema |
| `parameters` | Fully validated, normalized typed parameters |
| `risk_class` | Backend-derived classification, not client supplied |
| `required_permission` | Backend-derived permission, currently P1 for planning only |
| `mode` | Explicit `dry_run`; no alternate mode accepted in this stage |
| `plan_digest` | Digest of canonical action identity and all material parameters |
| `created_at` | Backend timestamp |
| `expires_at` | Backend timestamp after which the action is invalid |

Canonicalization requirements:

- Use a deterministic serialization with fixed field ordering, explicit types, normalized string encoding, and unambiguous null/absent handling.
- Reject unknown fields, duplicate keys, invalid types, out-of-range values, and non-canonical forms before creating an envelope.
- Include every parameter that can affect the proposed operation, including each program name, version/edition choice, source identifier, install scope, dependency choice, and order when applicable.
- Do not include secrets in the envelope or digest. Reject secret-bearing parameters unless a separately approved contract defines their safe handling.
- A digest is an integrity/binding aid, not authentication, user identity, or proof that a human approved the action.
- The digest algorithm and canonicalization format must be versioned and fixed by the backend. Algorithm selection remains an implementation decision for P5-504.

## 4. Confirmation/review record

If a review acknowledgement is later implemented, it should be represented by a backend-owned, short-lived, one-time record containing only:

- opaque review/confirmation identifier;
- action identifier and plan digest;
- state;
- creation and expiry timestamps;
- consumed timestamp, if consumed;
- revocation reason code, if revoked.

Do not store the original chat prompt, full conversation, or task history in this record. Avoid copying full parameters if the immutable action record can be referenced safely. Any durable storage or retention decision must be resolved in P5-506 before implementation.

For a future execution-capable design, a separate authorization record would be required; a P1 review acknowledgement must never be upgraded or reused as an execution authorization.

## 5. Proposed lifecycle

### Current P1 dry-run lifecycle

1. **RECEIVED** — accept the request through existing local API protections.
2. **VALIDATED** — validate fixed tool ID and strict typed parameters; reject unknown or malformed input.
3. **PLANNED** — backend creates the exact proposed program list and ordered dry-run plan.
4. **PRESENTED** — UI displays the full plan, including every program, version certainty, source proposal, dependencies, order, known impacts, and uncertainty.
5. **ACKNOWLEDGED or DECLINED** — optional user acknowledgement records only that the plan was reviewed; it does not grant execution permission.
6. **EXPIRED** — plan/review reference is no longer valid after its bounded lifetime.
7. **CANCELLED** — user cancels; no further action occurs.

At every state, outcome remains **Dry-run only — no changes made**. There is no transition from this lifecycle to an execution handler.

### Future execution lifecycle (design placeholder only; disabled)

A future separately approved capability would need a distinct lifecycle such as:

`PROPOSED → VALIDATED → AWAITING_CONFIRMATION → CONFIRMED → CONSUMED → EXECUTION_RESULT`

with terminal states `DECLINED`, `CANCELLED`, `EXPIRED`, `REVOKED`, and `REJECTED`.

This is a design placeholder, not an implementation instruction or authorization. The transition to `CONSUMED` would require atomic one-time consumption before any permitted handler dispatch. It must not be reachable under current P1.

## 6. Expiry, replay, cancellation, and revocation

Proposed defaults for later Product Owner review:

- Review/action references are short-lived and expire after **10 minutes**. This is a proposal, not an approved implementation value.
- Expiry is checked by the backend using its own clock at every state transition; client timestamps are never trusted.
- Expired records cannot be renewed in place. A fresh validated plan and fresh review are required.
- Every acknowledgement/authorization identifier is single-use. Replays return a generic rejected/expired response and cannot reach a handler.
- Cancellation is idempotent and terminal. A cancelled record cannot be reactivated.
- Backend restart invalidates all in-memory pending references unless a separately approved persistence design provides equivalent safe expiry and revocation semantics.
- Token rotation or local authorization reset invalidates pending references.
- Revocation is terminal and takes precedence over confirmation.
- Clock rollback, clock uncertainty, missing state, or state-store failure causes rejection; never extend expiry to compensate.
- Concurrent submissions must be serialized or atomically guarded so only one transition can consume a one-time record.

The 10-minute expiry and restart behavior require explicit review in P5-508; P5-504 must assess implementation feasibility and race safety.

## 7. Parameter changes and plan regeneration

Any change to any material field creates a new action identity and digest. This includes:

- adding or removing a program;
- changing program name, publisher/package identifier, version, edition, architecture, source, or installation scope;
- changing dependency list or installation order;
- changing flags/options that affect the proposed action;
- changing the tool contract version or risk/permission classification.

The prior review/confirmation becomes invalid. The backend must generate a new plan and show the complete changed list. The UI must not silently carry acknowledgement across a changed plan.

For the user's key requirement, the exact per-program Installation Plan is part of the bound content. The Agent must display the full program list before the user acknowledges the plan. A generic summary such as "install Java tools" is not sufficient.

## 8. API contract sketch (non-normative)

Names and routes below are illustrative only; P5-504 owns the final backend architecture.

| Operation | Purpose | Current P1 behavior |
|---|---|---|
| Create plan | Validate request and produce plan envelope | Allowed only for fixed dry-run tools |
| Read plan | Return exact plan and status | Allowed through existing local API authorization |
| Acknowledge plan | Record review of exact digest | Optional; no permission grant and no execution side effect |
| Decline/cancel plan | Close the review | Allowed; no execution side effect |
| Execute action | Dispatch machine-changing handler | **Not available; must not be implemented in P1** |

Client requests must not be allowed to submit `risk_class`, `required_permission`, `handler_name`, `execution_mode`, `approved=true`, or equivalent authority fields. The backend derives trusted metadata itself.

All state-changing endpoints remain subject to the existing Host/Origin, JSON content-type, local token, and request-size protections. This proposal does not weaken or replace those controls.

## 9. Failure behavior

The backend rejects before handler dispatch when any of the following occurs:

- unknown tool or unsupported action;
- malformed, extra, duplicate, or out-of-range parameters;
- missing or inconsistent backend policy;
- action/digest mismatch;
- changed plan after review;
- missing, invalid, expired, declined, cancelled, revoked, or already-consumed reference;
- duplicate or concurrent replay;
- unavailable or inconsistent state;
- clock uncertainty or expiry calculation failure.

Responses should use bounded reason codes and avoid leaking secrets or internal state. A rejected request must not trigger a fallback handler, shell command, external lookup, or partial machine operation.

## 10. Acceptance criteria

- P1 remains dry-run/report only; no execution transition or handler exists in the current scope.
- Plan review acknowledgement is clearly distinct from execution authorization.
- The exact program list and all material per-program parameters are bound to the plan digest.
- Any parameter change invalidates the prior review/confirmation.
- Expiry, one-time use, cancellation, revocation, restart, and concurrency semantics are explicit.
- Backend owns all trusted metadata and state transitions; UI/model/client cannot grant permission.
- Invalid or uncertain state fails closed before handler dispatch.
- No chat/task history or secrets are persisted by this contract.
- No runtime code, tests, machine inspection, downloads, provider calls, or execution are part of P5-503.
- P5-504 and P5-506 must resolve backend feasibility and storage/retention questions before implementation is proposed.

## 11. Open decisions for Product Owner

1. Approve the distinction between P1 plan-review acknowledgement and future execution authorization.
2. Approve or revise the proposed 10-minute review-reference expiry.
3. Approve or revise restart invalidation and one-time-use semantics.
4. Confirm that the exact per-program Installation Plan is part of the immutable bound content.
5. Decide whether a P1 acknowledgement record is needed at all; the dry-run may simply display the plan without storing an acknowledgement.

No decision is assumed from silence.
