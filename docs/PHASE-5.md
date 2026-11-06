# Phase 5 — Safety and Permission System

## Status

**Planning authorized by the Product Owner on 2026-11-02.** Runtime work is authorized only per explicitly approved bounded task: I1 / P5-510 is complete and merged in PR #58; I2 / P5-511 is authorized and in progress. These task approvals do not authorize real PC actions, Phase 6 execution, or any subsequent runtime task.

Phase 4 closeout was explicitly approved by the Product Owner on 2026-11-02. Its Windows verification evidence is recorded in the conversation and commit `8233af5`: 75 backend tests passed, 22 frontend tests passed, and Ruff passed. The corresponding repository status documents are being reconciled in this planning change.

## Objective

Design and verify a backend-enforced safety boundary for future PC automation. The system must classify risk, validate exact parameters, enforce permission levels, require explicit user confirmation where applicable, restrict executable capabilities, and provide appropriately minimized audit controls.

The AI model, planner, frontend, and client request must never grant permission to themselves. The backend is the enforcement authority.

## Governing constraints

- Preserve the approved phase order (P-ORDER-1, option A).
- Phase 5 builds the safety and permission gate; it does **not** enable real machine-changing execution.
- Real execution remains blocked until Phase 5 is complete and explicitly approved, and each capability is separately authorized under Phase 6.
- Existing `software.install` and `software.remove` tools remain dry-run/mock only throughout Phase 5.
- No arbitrary shell, PowerShell, command prompt, script, process, dynamic import, or raw model-output execution.
- No file, registry, process, application, network, or system-setting inspection/change as part of planning or verification.
- Preserve loopback-only binding (D-SEC-5) and local API authorization (D-SEC-1).
- Preserve Host/Origin checks, JSON-only state-changing requests, rejection of state-changing requests without Origin, development-only API docs, and the 16 KiB request-body limit (D-SEC-2 through D-SEC-4).
- Exception: the Product Owner separately authorized T-601 Gemini text-chat MVP on 2026-11-03. It sends only the current message to Gemini, stores the API key in backend process memory only, and does not enable provider tool/function calling or PC actions. This exception does not authorize any other provider, chat-history transfer, or broader external data flow.
- Do not persist chat messages, chat history, or task history. Audit design must respect data minimization and must not silently introduce content retention.
- Documentation/planning may proceed when consistent with approved decisions. Runtime changes require bounded tasks, tests, A4 review, and explicit Product Owner merge approval.
- Branch convention: `<type>/<task-id>-<short-name>`.

## Existing security baseline to preserve

- A random per-installation 256-bit local API token is stored in ignored `.env`, injected by the Angular development proxy server-side, and checked by the backend using constant-time comparison.
- Missing, invalid, or duplicate `X-Local-Agent-Token` headers are rejected for `/api/*`; `/health` remains unauthenticated by design.
- The local API token authorizes requests from the local development proxy; it does **not** identify a human user or count as explicit approval for a sensitive action.
- Backend middleware validates Host and Origin, rejects state-changing requests without Origin, requires JSON for state-changing requests, and enforces a 16 KiB request limit.
- The tool catalog is backend-owned and immutable. It currently contains only `software.install` and `software.remove`, both high-risk and dry-run-only.
- Tool request/result models are strict and frozen; dispatch uses a fixed handler map.
- Agent planning is deterministic and local; no provider is connected.
- Phase 4 UI shows plan, prerequisites, dry-run result, and approval-required information. It has no execute/approve-and-execute control.

## Workstreams (coordinator-managed four-role workflow)

These are parallel **planning and review lanes**, not four autonomous LLM processes or permission-bearing agents.

| Workstream | Role | Planning responsibility | Boundary |
|---|---|---|---|
| A1 — Coordinator / Product Analyst | Scope and contracts | Define risk/permission vocabulary, task dependencies, decision log, and cross-document consistency | Cannot make Product Owner decisions |
| A2 — Backend Engineer | Enforcement architecture | Read-only audit of current backend boundaries; propose backend-owned permission and confirmation contracts | No runtime edits or execution path in this planning stage |
| A3 — Frontend / UX Engineer | Confirmation UX | Specify clear action summary, parameter display, confirmation/cancel/expiry states, and accessible Thai-default bilingual flow | UI is never the authority; no execute button |
| A4 — QA / Security Reviewer | Threat model and verification | Threat model, abuse cases, negative tests, fail-closed criteria, audit/privacy review | Cannot approve or merge its own work |

## Planning tasks and dependencies

| Task | Owner | Deliverable | Depends on | Status |
|---|---|---|---|---|
| P5-501 | A4 | Threat model and current security-boundary audit — docs/P5-501-THREAT-MODEL.md | Existing Phase 2–4 baseline | Complete — read-only review; no code/tests run |
| P5-502 | A1 + A4 | Risk classification and permission-level proposal — docs/P5-502-RISK-PERMISSION-PROPOSAL.md | P5-501 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-503 | A1 + A2 | Confirmation lifecycle and exact-action binding contract — docs/P5-503-CONFIRMATION-CONTRACT.md | P5-502 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-504 | A2 + A4 | Backend enforcement architecture and fail-closed design — docs/P5-504-BACKEND-ENFORCEMENT-ARCHITECTURE.md | P5-502, P5-503 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-505 | A3 + A1 | Thai-default bilingual confirmation UX/API contract — docs/P5-505-DRY-RUN-UX-API-CONTRACT.md | P5-503 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-506 | A1 + A4 | Audit event model, privacy, retention, and access proposal — docs/P5-506-AUDIT-PRIVACY-RETENTION-PROPOSAL.md | P5-501, P5-502 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-507 | A4 | QA/security matrix, abuse tests, and acceptance evidence plan — docs/P5-507-QA-SECURITY-MATRIX.md | P5-502 through P5-506 | Proposal drafted; PO decisions approved; reconcile to P5-508 |
| P5-508 | A1 + A4 | Integrated Phase 5 design review and Product Owner decision packet — docs/P5-508-INTEGRATED-DESIGN-DECISION-PACKET.md | P5-501 through P5-507 | All 12 PO decisions approved and recorded |
| P5-509 | A1 + A2 + A3 + A4 | Approved design reconciliation and bounded runtime task breakdown — docs/P5-509-IMPLEMENTATION-BREAKDOWN.md | P5-508 | Planning complete; P5-510 complete; P5-511 authorized/in progress |

P5-501 read-only threat model is complete: docs/P5-501-THREAT-MODEL.md. It confirms that the existing local API token is not human identity or proof of action consent.\n\nParallel work is limited to independent read-only analysis. Contracts must be reconciled before any implementation task is proposed. No dependent task may bypass an unresolved decision.

## Approved design decisions and remaining gates

All 12 P5-508 decisions were explicitly approved by the Product Owner on 2026-10-30 using the recommended safe defaults. The detailed decision register is in `docs/P5-508-INTEGRATED-DESIGN-DECISION-PACKET.md`. P5-502 through P5-507 are reconciled for implementation planning in `docs/P5-509-IMPLEMENTATION-BREAKDOWN.md`. The backlog is planning only; it does not authorize runtime implementation. D-P5-12 requires a separate explicit instruction.

1. Risk classes, thresholds, and the exact mapping from tool/action to risk.
2. Permission levels, their scope, and whether permissions are per action, per session, or another bounded unit.
3. Confirmation mechanics: exact parameter binding, expiry, one-time use, cancellation, replay prevention, and behavior if parameters change.
4. Whether confirmation requires re-authentication or another local user-presence signal beyond the existing local API token.
5. How the backend safely represents and validates a proposed action without accepting arbitrary commands or paths.
6. Audit event fields, storage location, retention, redaction, and whether any durable security event record is permitted under the no-chat/task-history rule.
7. How permission revocation, application restart, token rotation, clock changes, and concurrent requests behave.
8. Which actions remain permanently unsupported or require separate Phase 6 authorization.

Any proposed change to the approved data-retention, local-exposure, provider/data-flow, or safety boundary must return to the Product Owner before implementation.

## Acceptance criteria for the Phase 5 design

- Risk classes and permission levels are explicit, testable, and mapped to backend-owned tool definitions.
- Confirmation is enforced by the backend; model output and frontend state cannot approve an action.
- The design binds any approval to one exact action and its validated parameters, with a defined expiry and replay policy.
- Parameter validation is strict, bounded, typed, and fail-closed.
- No arbitrary command or dynamic handler execution is introduced.
- Denied, missing, expired, mismatched, replayed, or revoked authorization cannot reach an execution handler.
- Audit controls are defined without storing chat messages or task history and with explicit retention/redaction rules.
- Existing loopback, local API token, Host/Origin, content-type, and request-size controls remain intact.
- Tests cover negative/abuse cases and prove that Phase 5 verification itself has no machine-changing side effects.
- A4 reviews source, diffs, threat model, tests, and limitations.
- Product Owner explicitly approves Phase 5 closeout before any Phase 6 real-execution work begins.

## Phase 5 implementation gate

After the planning tasks are reviewed, implementation must be split into bounded tasks and branches. Each runtime task requires explicit Product Owner authorization before work begins and explicit approval before its code PR is merged. Authorization for one task does not authorize the next task.

All implementation and verification during Phase 5 must use mocks/dry-runs. Completing Phase 5 does not automatically enable real execution. Phase 6 and each individual tool still require separate authorization.

## Definition of done

- All planning tasks and design questions are resolved or explicitly deferred by the Product Owner.
- The threat model, risk/permission matrix, confirmation contract, backend enforcement design, UX contract, audit/privacy policy, and QA matrix are consistent.
- Required runtime tasks have bounded scope, dependencies, tests, and safety statements.
- A4 review is complete and evidence is recorded.
- Product Owner explicitly approves Phase 5 closeout.
