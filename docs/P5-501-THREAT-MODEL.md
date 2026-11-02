# P5-501 — Phase 5 Threat Model and Security-Boundary Audit

## Status

**Read-only source review complete (2026-11-02).** Reviewed the current GitHub `main` baseline at `8233af5`, including Phase 2 security decisions, Phase 3 authorization and Agent boundaries, Phase 4 tool/task implementation, and the Phase 4 QA/security matrix. No code was executed or changed as part of this review.

This is a threat-modeling artifact, not an authorization to implement permissions or perform PC actions. Recommended controls below remain design recommendations until accepted in the Phase 5 decision process.

## System and security objectives

Protect a Windows 11 PC controlled through a loopback-only Angular application and FastAPI backend. The safety system must ensure that:
- Only backend-defined capabilities can be requested.
- Every action is validated against backend-owned schemas and policy.
- The model, browser, request payload, and UI cannot grant permission.
- Sensitive actions require explicit user confirmation under a defined policy.
- Denied or invalid actions fail closed before reaching any handler.
- Audit evidence is minimized and does not become chat/task-history storage.
- No real machine-changing execution is enabled by Phase 5 itself.

## Assets

| Asset | Security objective | Current state |
|---|---|---|
| Local API token | Confidentiality and integrity | Random 256-bit per-installation token in ignored `.env`; injected by local Angular proxy; backend constant-time comparison |
| Tool catalog and handler map | Integrity | Backend-owned immutable catalog and fixed handler mapping |
| Tool request parameters | Integrity and validation | Strict, frozen Pydantic request model; target bounded to 1–120 characters |
| User intent and messages | Confidentiality | Request processing is local/deterministic; chat/task history is not persisted |
| Permission grants | Prevent unauthorized actions | Not implemented; Phase 5 scope |
| Confirmation challenges/receipts | Prevent forgery, replay, and parameter substitution | Not implemented; Phase 5 design required |
| Audit/security events | Accountability with data minimization | No Phase 5 audit-event contract or retention decision yet |
| PC state and applications | Prevent unauthorized modification or inspection | No real PC inspection or modification capability approved |

## Trust boundaries

1. **Browser/UI → local development proxy:** Browser content is untrusted. The local API token must not be embedded in frontend assets or exposed to page JavaScript.
2. **Proxy → backend API:** Backend verifies the local token and request boundary. The token proves possession of a local installation secret; it does not identify a human or prove consent.
3. **User request/model/planner → backend tool layer:** Request text and any future model output are untrusted proposals, never authority.
4. **Backend policy → tool handler:** Only validated backend-owned tool definitions and fixed handlers may cross this boundary.
5. **Backend → Windows PC:** Currently no real machine-changing execution path is approved. Existing install/remove handlers return dry-run previews only.

## Threat actors and scenarios

| ID | Threat actor / condition | Threat scenario | Impact | Existing mitigation / gap |
|---|---|---|---|---|
| TM-01 | Malicious website in browser | Cross-origin page sends requests to localhost | Unauthorized Agent requests | Host/Origin checks, Origin required for state-changing requests, JSON-only state-changing requests, local token |
| TM-02 | Malicious or compromised browser extension | Reads page data or attempts to drive local UI/API | Unauthorized request or data exposure | Token is injected by proxy, not browser bundle; local process compromise remains outside this boundary |
| TM-03 | Untrusted local process under same OS account | Reads local `.env` or calls backend with the token | Bypasses the browser-origin boundary | Token is a local API authorization secret, not a user identity control; stronger OS isolation is not in current scope |
| TM-04 | Malformed or malicious API client | Sends duplicate headers, oversized body, invalid content type, wrong Host/Origin | Middleware bypass or denial of service | Duplicate token/Host/Origin checks, JSON requirement, 16 KiB body limit, strict validation |
| TM-05 | Prompt injection / untrusted model output (future provider) | Model proposes a dangerous tool, command, or altered target | Unauthorized PC action | No provider is connected; closed tool catalog and strict schemas; provider integration remains unapproved |
| TM-06 | Client or model attempts privilege escalation | Adds risk, permission, approval, executable, command, or status fields | Client-controlled authorization or arbitrary execution | Current strict schema rejects extra fields; Phase 5 must keep policy fields backend-owned |
| TM-07 | Replay or parameter substitution | Reuses an approval for another target or modified parameters | User approves one action but another executes | No confirmation system exists; exact-action binding, expiry, and replay policy are Phase 5 design questions |
| TM-08 | Concurrent requests / race | Two requests consume the same approval or race a revoke/expiry | Duplicate or unintended action | No permission/confirmation state exists; atomic single-use semantics need design and tests |
| TM-09 | Logging or diagnostics | Sensitive request, token, or action data is written to logs | Secret or personal-data leakage | Current error responses scrub exception details; Phase 5 audit fields and redaction/retention are undecided |
| TM-10 | Configuration or startup failure | Missing/invalid token or policy config falls back to permissive behavior | Authorization bypass | Token configuration fails startup; Phase 5 policy/configuration must also fail closed |
| TM-11 | Handler or dependency regression | New handler introduces filesystem, process, network, registry, or OS side effects | PC inspection/change outside approved scope | Current handlers are dry-run only; source review and no-side-effect tests required for every future capability |
| TM-12 | Local network exposure | Service binds to LAN interface | Remote clients reach local Agent | Loopback-only binding is a standing rule (D-SEC-5) and startup rejects non-loopback host |

## Existing controls verified in source

- Backend startup rejects non-loopback `BACKEND_HOST` values.
- Local API token must be 64 lowercase hexadecimal characters (32 random bytes); it is read from local environment configuration.
- The backend requires exactly one `X-Local-Agent-Token` header on `/api/*` and compares it with `hmac.compare_digest`.
- Host is allowlisted; Origin is checked; state-changing requests without Origin are rejected.
- State-changing requests require exactly one JSON content type.
- Request bodies are limited to 16 KiB, including streamed bodies.
- Tool catalog contains only `software.install` and `software.remove`; both are high-risk and dry-run-only.
- Tool request/result/definition models are strict and frozen; the handler map is immutable and fixed in code.
- Agent core is deterministic and local; no provider call is made.
- Task status is request-scoped; no chat/task-history persistence is implemented.
- Phase 4 UI has no execute or approve-and-execute control.

## Gaps that Phase 5 must address

1. No risk-to-permission policy contract exists beyond current tool metadata marking both tools high-risk.
2. No backend permission grant, revoke, or scope model exists.
3. No explicit user-confirmation challenge or receipt exists.
4. No exact-parameter binding, expiry, replay protection, or atomic single-use consumption exists.
5. No explicit audit-event schema, redaction policy, storage decision, or retention period exists.
6. The local API token is not a human identity signal and must not be reused as proof of action approval.
7. There is no approved mechanism for privileged execution; arbitrary commands and dynamic handler dispatch must remain prohibited.

## Recommended security properties for design review

These are properties to evaluate, not yet a finalized implementation contract:

- **Backend authority:** risk, permission, approval state, and handler selection are derived from backend-owned definitions.
- **Fail closed:** missing policy, unknown tool, malformed parameters, unavailable confirmation state, or internal policy errors deny the action.
- **Exact-action approval:** any future approval should be bound to a canonical action identity and its fully validated parameters; changing any parameter invalidates it.
- **Bounded confirmation:** define expiry, cancellation, one-time consumption, replay behavior, and concurrency semantics before implementation.
- **Revalidation:** re-check policy and parameters immediately before any handler is invoked.
- **No implicit escalation:** model output, frontend flags, local API token, and task status cannot elevate permission.
- **Minimal audit:** record only approved security metadata; never log secrets, full chat messages, or task history. Do not persist audit events until retention and storage are explicitly decided.
- **No Phase 5 execution:** use mocks/dry-runs for all tests and demonstrations.

## Verification and limitations

- Method: read-only review of GitHub source and project documentation.
- No local Windows command was run by A4 during this review.
- No runtime tests were run because no code changed.
- No exploit testing against the user's PC was performed or authorized.
- No real installation, removal, file access, process inspection, registry access, network discovery, or system-setting operation was attempted.
- This review does not establish that a future confirmation or permission implementation is secure; it defines threats and properties that later design and tests must address.

## Handoff

P5-501 provides inputs to:
- P5-502: risk classification and permission-level proposal.
- P5-503: confirmation lifecycle and exact-action binding contract.
- P5-506: audit event, privacy, and retention proposal.

Do not begin runtime implementation until the design tasks are reconciled and the Product Owner explicitly authorizes a bounded implementation task.
