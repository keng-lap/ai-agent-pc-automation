# P5-509 — Approved Design Reconciliation and Runtime Task Breakdown

## Status and authority

**Documentation/planning deliverable.** The Product Owner approved all 12 P5-508 decisions on 2026-10-30 using the recommended safe defaults. This document translates those decisions into a bounded implementation backlog and resolves conflicts in P5-502 through P5-507.

This document is the planning baseline and does not itself authorize runtime work. P5-510 through P5-513 are complete and merged (PRs #58, #61, #63, #64). P5-514 was completed and merged in PR #65 (commit `463457b`). The Product Owner explicitly authorized P5-515 on 2026-11-07. Its initial negative/abuse/regression test increment was merged in PR #66; merge-commit CI run `42355435380` passed backend tests, Ruff, frontend unit tests, and frontend build on commit `3d661d7`. P5-515 evidence/matrix reconciliation remains in progress. P5-516 remains gated pending P5-515 closeout evidence and separate independent review. Phase 6 and real PC actions remain unauthorized.

## 1. Binding design baseline

1. Risk classes R0–R3 are backend-derived. R2 and R3 are denied in Phase 5.
2. Permission levels P0–P3 are backend-owned. P1 is the only active tool permission; P2/P3 are hard-denied. No client, model, environment-variable, or user-editable override.
3. Any short-lived plan/review reference expires after 10 minutes, using backend time.
4. Pending in-memory references are invalidated on restart. Any future one-time state transition must be atomic and replay-safe.
5. The exact immutable per-program plan and every material parameter are bound together. Any change creates a new plan identity/digest.
6. No acknowledgement is required in the current P1 workflow. Displaying the dry-run report is sufficient. No acknowledgement endpoint, button, event, or confirmation lifecycle is to be implemented for P1.
7. Thai is the default UI language; English is selectable. API routes and response contracts must be reconciled against the existing API before implementation.
8. Audit option A is selected: bounded in-memory security events, cleared on restart. Durable logs, browser storage, databases, and external telemetry are prohibited.
9. Audit fields and event types are strict allowlists. No prompts, full plans, secrets, raw parameters, machine inventory, raw exception text, or stack traces.
10. Mandatory policy evaluation failure denies before dispatch. Optional diagnostics failure must not create a permissive fallback or cause unbounded/raw logging.
11. Implementation must be split into bounded tasks with dependencies and acceptance criteria.
12. Runtime implementation and verification are authorized only per explicitly approved bounded task. P5-510 through P5-514 are complete. The Product Owner separately authorized P5-515 on 2026-11-07; P5-515 verification is in progress following PR #66. This does not authorize P5-516, Phase 6, or real PC actions.

## 2. Reconciliation of P5-502 through P5-507

- **P5-502:** Adopt R0–R3/P0–P3. P1 plan/report only. R2/R3 and P2/P3 deny. Preserve explicit per-program installation list and the statuses `PLANNED`, `NEEDS_CLARIFICATION`, `BLOCKED`, `UNSUPPORTED`. Optional programs are omitted unless requested; never silently add them.
- **P5-503:** Retain immutable plan identity, full material-parameter binding, 10-minute backend expiry, restart invalidation, and fail-closed state semantics. Remove current-P1 acknowledgement/decline/consume lifecycle from implementation scope because D-P5-06 says no acknowledgement is required. Future execution confirmation remains a separate, disabled design requiring new approval.
- **P5-504:** Implement a backend-owned immutable policy decision point and final pre-dispatch guard. Preserve existing HTTP boundary controls. The handler map remains fixed; policy must be checked immediately before dispatch. No fallback, dynamic handler, shell, process, package manager, OS inspection, or real execution.
- **P5-505:** Keep Thai-default/English-selectable report UX and all per-program fields. Remove acknowledgement and cancel controls/routes from the current P1 scope unless a non-machine-changing cancel operation is demonstrably needed and separately specified. No execute/install/remove control or endpoint.
- **P5-506:** Implement only bounded ephemeral in-memory events. Initial engineering proposal: maximum 500 events, evict oldest first, clear on process restart. This cap is an implementation parameter to document and test; it does not permit durable storage. Event sink failure is non-blocking only for optional diagnostics; policy evaluation failure remains deny.
- **P5-507:** Retain the negative/security matrix but revise acknowledgement-specific cases (Q17–Q21) to test that no acknowledgement API/state exists in P1 and that plan changes create a new identity. Keep fake handlers, fake clock, no side effects, evidence capture, and independent A4 review.

## 3. Bounded implementation backlog and status

| Task | Owner lane | Scope | Dependencies | Acceptance gate | Status |
|---|---|---|---|---|---|
| I1 / P5-510 — Static policy model and startup validation | A2 + A4 | Immutable versioned R0–R3/P0–P3 matrix; fixed catalog mapping; startup consistency checks; hard deny P2/P3 | P5-509 | Missing/duplicate/unknown policy fails closed; no caller override; unit tests | Complete — merged in PR #58 |
| I2 / P5-511 — Central policy decision and final dispatch guard | A2 + A4 | Insert backend policy decision point and final guard immediately before fixed handler dispatch; typed deny reasons | I1 | Spy handler proves every invalid/denied path is blocked; only P1 dry-run handlers reachable | Complete — merged in PR #61 (commit 2875399) |
| I3 / P5-512 — Immutable dry-run plan/report contract | A2 + A3 | Strict per-program plan schema, canonicalization/versioned digest, 10-minute backend expiry, restart invalidation; no acknowledgement state | I1, I2 | Exact material fields affect identity; mutation yields new identity; no prompt/secret persisted | Complete — merged in PR #63 |
| I4 / P5-513 — Ephemeral audit event sink | A2 + A4 | Allowlisted event schema; max 500 in-memory events; oldest-first eviction; restart clears; no durable sink | I1, I2 | Reject forbidden fields; bounded memory; optional sink failure cannot cause unsafe fallback | Complete — merged in PR #64 |
| I5 / P5-514 — Thai-default bilingual UX and API integration | A3 + A2 | Reconcile existing routes; display request, interpretation, every program, uncertainty, status, dry-run/no-change notice; bounded clarification creates a new immutable plan; English selectable | I3 | No acknowledgement/execute controls or endpoints; accessible mobile/desktop rendering | Complete — merged in PR #65 (commit `463457b`) |
| I6 / P5-515 — Negative, abuse, and regression verification | A4 | Update and execute relevant P5-507 matrix using synthetic fixtures, fake clock, spy handlers; verify existing HTTP protections | I1–I5 | Actual commands, exit codes, outputs, SHA, environment and limitations recorded; zero real side-effect capability | In progress — initial test increment merged PR #66; CI passed; evidence/matrix reconciliation tracked in `docs/P5-515-VERIFICATION-EVIDENCE.md` |
| I7 / P5-516 — Independent security review and Phase 5 evidence pack | A4 independent reviewer | Review implementation diffs, test evidence, threat-model coverage, policy/dispatch boundaries, privacy and regression | I1–I6 | A4 review findings resolved or explicitly documented; no self-review | Not started — independent review |

Task IDs and ordering define the approved backlog. P5-510 through P5-514 are complete. P5-515 is authorized and in progress; PR #66 is merged and its merge-commit CI passed, while evidence/matrix reconciliation remains open. P5-516 still requires separate authorization. No real machine-changing action is authorized.

## 4. Dependency order and parallel lanes

`I1 → I2 → I3 → I5`; I4 depends on I1/I2 and can proceed in parallel with I3. I6 begins only after I1–I5 are complete. I7 is independent review after implementation and evidence are available.

The four workstreams are coordination lanes, not four autonomous permission-bearing agents:
- A1 coordinates scope, dependencies, decision register, and cross-document consistency.
- A2 owns backend design/implementation.
- A3 owns UX/API contract and frontend.
- A4 independently owns security review and verification.

No lane may self-approve a Product Owner decision or merge a runtime PR.

## 5. Global non-negotiable constraints

- P1 dry-run/plan/report only; no machine change.
- P2 inspection and P3 execution remain hard-denied.
- No arbitrary shell/PowerShell/CMD/script/process execution.
- No filesystem, registry, process, installed-software, network, or system-setting inspection.
- No provider, live model, package source lookup, package manager, credentials, or external transfer.
- No chat/task history; no durable audit; no prompts/full plan in audit events.
- Preserve loopback-only binding, local API token semantics, Host/Origin, JSON-only state-changing requests, and 16 KiB body limit.
- Backend is the authority; model/frontend/client never grant permission.
- Fail closed before handler dispatch. No fallback/retry with broader capability.
- Existing `software.install` and `software.remove` remain dry-run/mock only.
- Runtime code PRs require explicit PO approval before merge. Documentation-only PRs may use the standing docs-only merge permission after exact diff confirms all changed paths are under `docs/`.

## 6. Evidence and current status

I1 / P5-510 is complete and merged in PR #58. I2 / P5-511 is complete and merged in PR #61 (commit 2875399). Its implementation and verification used synthetic inputs and dry-run handlers only; no machine-changing operation was performed.

**Current gate:** P5-510 through P5-514 are complete and merged (PRs #58, #61, #63, #64, and #65). P5-515 is authorized and in progress; PR #66 is merged and merge-commit CI run `42355435380` passed. Remaining P5-515 work is evidence/matrix reconciliation and review of existing test coverage. P5-516 is a separate independent review and has not started; it requires separate authorization. Phase 6 and real PC execution remain unauthorized.


## 7. P5-517 — Approval-gated P1 Dry Run (Product Owner authorized 2026-11-07)

This task supersedes backlog item 6's earlier “no current-P1 acknowledgement/approval” implementation assumption only for the bounded P1 Dry Run gate. The original P5-508 D-P5-06 remains historical; the binding replacement is D-P5-13 in the P5-508 decision packet.

**Required flow:** Gemini-assisted plan → display exact immutable plan → user explicitly approves that plan → backend verifies plan identity/digest, eligibility, and 10-minute TTL → fixed dry-run handler runs once for every listed program → UI displays the result and an explicit no-machine-changes notice.

**Implementation findings on main at task start (commit `5bd9225365d777202e144eef535a7a93e67d762f`):**
- The approval API, frontend approval button, and approval client call already exist.
- Existing tests cover a single dispatch and replay caching, but the approval test's Java fixture contains two programs while the implementation dispatches only the first program. This could misrepresent a partially simulated plan as complete.
- Existing P5-507/P5-515 documentation and the OpenAPI allow-list test did not consistently describe/assert the approval route.

**P5-517 scope:**
1. Dispatch the fixed dry-run handler once for each program in the exact immutable approved plan; aggregate a result that names every program.
2. Restore the P5-514 architecture: the backend builds the trusted typed review plan deterministically from the original user request and does not make a second Gemini call or parse Gemini chat prose. Treat an explicitly named software install/remove target as sufficient for a P1 preview; show unknown version/source/impact as unverified. Preserve mandatory Java clarification questions. Keep approval server-owned and exact-plan-bound; preserve 10-minute expiry, restart invalidation, clarification blocking, and replay protection (cached result; no second dispatch).
3. Explicitly assert the sole `POST /api/plans/{plan_id}/approve` state transition in the API allow-list tests; keep acknowledgement/cancel/execute routes absent.
4. Update Q15/Q17 and the superseding Product Owner decision record.
5. Run backend tests, Ruff, frontend unit tests, and frontend production build in CI. Record actual commit and CI evidence before asking the Product Owner to test locally.

**Acceptance tests:**
- Plan creation never dispatches a dry-run handler.
- An explicit request such as `ติดตั้ง Google Chrome` creates a `PLANNED` preview without a second Gemini provider call; optional version/channel details remain visibly unspecified and do not block this P1 preview.
- The plan API must remain available after the chat response even if Gemini structured-output generation is unavailable, because it uses the deterministic backend planner.
- Approval of an eligible two-program plan dispatches exactly those two program targets once each.
- Repeating approval returns the cached result without another handler call.
- Any plan item needing clarification blocks approval before dispatch.
- A changed/refined plan has a new identity and requires a new approval.
- The API exposes only the approval transition; acknowledgement, cancel, execute, install, and remove routes remain absent.
- The UI exposes approval only when every listed item is `PLANNED`; the displayed result explicitly says no real PC changes occurred.
- No OS, filesystem, registry, process, network, package-manager, installer, or real machine-changing capability is added.

**Authority:** P5-517 runtime changes are authorized for implementation and CI verification only. The PR must remain unmerged until the Product Owner reviews the exact diff and explicitly approves merge. Phase 6 and real PC actions remain unauthorized.
