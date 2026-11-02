# P5-506 — Audit Event, Privacy, Retention, and Access Proposal

## Status and boundary

**Proposal for Product Owner review. Documentation only.** This proposal defines a minimal security-event model for the P1 dry-run workflow. It does not authorize runtime implementation, durable logging, machine inspection, external transfer, or any PC operation.

P1 remains dry-run/plan/report only. P2 inspection and P3 machine-changing actions remain disabled. Existing no-chat-history/no-task-history constraints remain in force. No retention or storage decision is approved by drafting or merging this proposal.

## 1. Goals and non-goals

Goals:
- Provide enough security-relevant evidence to diagnose denied or malformed requests and review the P1 plan lifecycle.
- Minimize data collection and prevent audit records from becoming a shadow chat/task history.
- Keep access local and bounded, with explicit retention and deletion behavior.
- Make policy decisions and lifecycle transitions attributable to server-generated identifiers and policy versions, not model claims.

Non-goals:
- Store prompts, chat messages, full plans, installation command lines, credentials, or user activity history.
- Prove the identity of a human or prove informed consent using the local API token.
- Record machine state, installed applications, files, registry, processes, network activity, or system settings.
- Send telemetry, logs, or audit events to a provider or external service.

## 2. Data classification

| Class | Examples | Proposed treatment |
|---|---|---|
| Secret | Local API token, credentials, private keys, session secrets | Never record; redact before error/log handling |
| User content | Original request, prompt, full interpretation, full per-program plan | Do not persist in audit events |
| Security metadata | Event ID, event type, UTC timestamp, policy version, bounded reason code | Candidate minimal event fields |
| Correlation metadata | Opaque plan reference, opaque request correlation ID | Optional; random, short-lived, not user identity |
| Operational diagnostics | Exception type, component code | Allowlisted bounded code only; no raw exception text or stack trace |

## 3. Proposed event vocabulary

Use a small allowlist of event types:
- `REQUEST_REJECTED`
- `POLICY_DECISION`
- `PLAN_CREATED`
- `PLAN_PRESENTED`
- `ACKNOWLEDGEMENT_RECORDED` (only if PO approves acknowledgement)
- `PLAN_DECLINED`
- `PLAN_EXPIRED`
- `PLAN_CANCELLED`
- `SAFE_FAILURE`

Events must not claim that a program was installed, removed, inspected, or changed. The current workflow cannot produce those outcomes.

## 4. Minimal event schema proposal

Candidate fields:

| Field | Requirement |
|---|---|
| `event_id` | Server-generated random identifier |
| `event_type` | Exact allowlisted enum |
| `occurred_at` | Server-generated UTC timestamp |
| `request_id` | Optional random correlation identifier, short-lived |
| `plan_id` | Optional opaque plan reference; no raw request content |
| `tool_id` | Fixed catalog ID only, when applicable |
| `policy_version` | Server-owned version, when a policy decision occurred |
| `decision` | Bounded enum such as allow-dry-run or deny |
| `reason_code` | Bounded allowlist; never free-form user/model text |
| `result_class` | Bounded outcome class, not raw result payload |

Do not include IP address, machine/user account name, hostname, file paths, package command strings, environment variables, request bodies, headers, token fragments, raw prompts, full parameters, or stack traces by default. Any proposed addition requires a separate necessity and privacy review.

## 5. Storage and retention options

Three options are presented for PO decision:

A. **No durable audit storage (privacy-first default recommendation):** security events exist only in bounded process memory for immediate diagnostics and disappear on restart. This is the safest fit for the current no-history requirement, but provides no durable forensic trail.

B. **Explicitly approved minimal durable security log:** only the allowlisted metadata schema above; local-only storage; strict size cap; rotation; fixed short retention period selected by PO; no content fields. This changes the data-retention boundary and must not be implemented without explicit PO approval.

C. **No event collection beyond safe error responses:** simplest privacy posture; limited diagnostic evidence.

No option is selected by this proposal. Recommendation: choose A for P1 unless the PO identifies a concrete need for durable security evidence. Do not assume option B is approved.

## 6. Access, redaction, and deletion

- No remote logging, analytics, telemetry, or external export.
- No frontend endpoint to browse raw security events unless separately approved.
- If local diagnostics are approved, expose only bounded, redacted reason codes; never expose secrets or raw content.
- Do not treat possession of the local API token as proof that a human is authorized to inspect sensitive audit data.
- Any durable record must have a documented owner, access boundary, retention period, rotation cap, and deletion procedure before implementation.
- On expiry/deletion, remove the event record and any associated index/reference; do not retain a hidden backup.
- Errors returned to clients must be generic and bounded. Detailed internal diagnostics must not leak through HTTP responses.

## 7. Retention and lifecycle

For ephemeral option A:
- Keep events in bounded memory only.
- Set a hard maximum event count and evict oldest entries.
- Clear all events on process restart.
- Do not persist event payloads to files, databases, browser storage, or task history.

For durable option B, all of the following remain unresolved and require explicit PO selection:
- Exact retention duration.
- Maximum bytes/events and rotation behavior.
- Whether records survive application restart.
- Deletion semantics and backup treatment.
- Whether export is prohibited or permitted.
- How access is authenticated without misrepresenting the local API token as human identity.

Plan expiry/cancellation from P5-503 is separate from audit retention. Expiring a plan must not silently preserve its request or full plan in an audit record.

## 8. Failure behavior

- If optional audit recording fails, do not fall back to an unbounded logger or write raw content elsewhere.
- Whether a failure to record a security event should block plan creation is a PO decision; safe default recommendation is fail closed for security-critical policy evaluation, but do not make ordinary optional diagnostics a hidden dependency.
- Never allow an audit subsystem to dispatch a tool or change a policy decision.
- Audit event contents are data, never executable instructions.

## 9. Acceptance criteria

- Event types and fields are strictly allowlisted and bounded.
- No prompt, chat history, full plan, credentials, token, raw parameters, stack trace, or machine inventory is stored.
- No external telemetry or export occurs.
- Access, retention, deletion, rotation, and restart behavior are explicit for the selected option.
- Audit failure cannot create a permissive fallback or reach a handler.
- Records cannot be mistaken for human identity or execution consent.
- Durable storage is not implemented until separately approved by the PO.
- P1 remains dry-run only; P2/P3 remain disabled.

## 10. Open decisions for Product Owner

1. Select A (ephemeral bounded memory), B (minimal durable security log), or C (no event collection).
2. If A, approve a bounded event count and restart-clears-all behavior during implementation planning.
3. If B, explicitly decide retention duration, size cap, rotation, access, deletion, and export policy before any code.
4. Approve or revise the event types and minimal field allowlist.
5. Decide whether acknowledgement events are needed if P5-505 acknowledgement is approved.
6. Decide whether optional audit failure blocks plan creation, separately from mandatory policy evaluation failure.

No decision is assumed from silence.
