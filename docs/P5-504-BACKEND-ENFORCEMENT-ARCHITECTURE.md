# P5-504 — Backend Enforcement Architecture and Fail-Closed Design

## Status

**Proposal for Product Owner review. Documentation only; read-only source audit.** This document proposes the backend enforcement boundary for Phase 5. It does not authorize runtime implementation, machine inspection, installation, removal, downloads, process creation, or execution.

Reviewed GitHub `main` at `68b860db81ab619f4b6363b1f1f0997ae83ea52a`. The active permission remains P1 — Dry-run / plan and report only. P2 machine inspection and P3 machine-changing execution remain disabled.

## 1. Executive design

Introduce one backend-owned policy decision point between validated requests and the fixed tool handler map. All tool dispatch must pass through that point. The policy decision is derived from trusted backend definitions and validated server-side context; it must never be accepted from the browser, request body, model, planner output, or local API token.

The enforcement pipeline should be:

`HTTP boundary → request schema validation → intent/tool matching → backend catalog lookup → risk/permission derivation → policy decision → dry-run-only handler dispatch → typed result validation`

Any missing, unknown, inconsistent, malformed, unsupported, or unavailable policy input results in denial before a handler is called. There is no permissive fallback and no dynamic handler lookup.

This is a design target for a future bounded implementation task, not permission to change runtime code now.

## 2. Read-only audit of current main

### 2.1 Existing controls to preserve

Source reviewed:

- `src/backend/agent_backend/main.py`
- `src/backend/agent_backend/security.py`
- `src/backend/agent_backend/config.py`
- `src/backend/agent_backend/chat.py`
- `src/backend/agent_backend/agent_core.py`
- `src/backend/agent_backend/tools.py`

Current protections observed:

- Backend configuration rejects non-loopback bind hosts.
- A 256-bit local token is validated at startup and checked with constant-time comparison on `/api/*`.
- Duplicate/missing local-token headers are rejected.
- Host is allowlisted; Origin is checked and required for state-changing requests.
- State-changing requests require exactly one JSON content type.
- Request bodies are capped at 16 KiB, including streamed bodies.
- Pydantic request, result, and tool-definition models reject extra fields; tool definitions are frozen.
- The catalog is a fixed tuple containing only `software.install` and `software.remove`.
- The handler map is a fixed `MappingProxyType`; request data cannot supply a callable or module name.
- Both current handlers produce dry-run previews only.
- Provider connection is disabled and the current planner is deterministic/local.
- No chat/task-history persistence is present in the reviewed flow.

These controls are baseline invariants. P5-504 must not weaken them.

### 2.2 Current enforcement gap

The current tool layer validates tool identity and target against planner intent, then `agent_core.run_agent` calls `execute_tool` directly. `execute_tool` resolves a fixed handler and validates the typed result, but there is no separate centralized policy decision point that independently derives and enforces risk class and permission level immediately before dispatch.

The catalog currently describes both tools as high-risk and dry-run-only. That metadata is descriptive and does not yet implement the proposed R0–R3 / P0–P3 policy matrix from P5-502.

The current design is still dry-run-only, so this is a Phase 5 architecture gap, not evidence of an active real-execution vulnerability. The proposed enforcement layer must keep all current handlers dry-run-only.

### 2.3 Scope and audit limitations

- This was a source/document review of GitHub main only.
- No source was executed, no tests were run, and no local PC was inspected.
- No exploit attempt or penetration test was performed.
- The audit does not prove the absence of every side effect in dependencies; future implementation requires targeted negative tests and A4 review.

## 3. Trusted policy model

### 3.1 Backend-owned inputs

The policy engine may use only:

1. Fixed tool definition loaded from the backend catalog.
2. Strictly validated and normalized tool parameters.
3. Server-derived request/task context needed to verify intent-to-tool consistency.
4. Backend policy version and static configuration.
5. Explicit backend-owned permission state, if a future approved design introduces it.

The following are never trusted policy inputs:

- Client-supplied risk class, permission level, approval flag, handler name, execution mode, or policy version.
- Model-generated claims that the user approved or that a task is safe.
- Frontend state, hidden controls, route guards, or disabled buttons.
- The local API token as human identity, user presence, or consent.
- Client timestamps or client-generated digests.
- Tool names, commands, paths, executable names, or argument vectors outside the fixed catalog schema.

### 3.2 Proposed static policy matrix

| Risk | Permission | Policy outcome in current stage |
|---|---|---|
| R0 informational | P0 | Allow informational response without machine capability |
| R1 planning | P1 | Allow bounded dry-run planning/report only |
| R2 machine inspection | P2 | Deny — permission disabled |
| R3 machine change / privileged | P3 | Deny — permission disabled |

Rules:

- Risk is the highest-impact class required by the requested operation.
- Permission does not follow from risk labels supplied by a caller; the backend derives required permission from the fixed tool/action definition.
- Only P0 and P1 are enabled for the current stage; P1 is the only active tool permission.
- P2/P3 must be explicit deny states, not merely absent UI options.
- Unknown action, unknown risk, missing mapping, policy version mismatch, or inconsistent catalog metadata is denied.
- No automatic downgrade from R2/R3 to R1 is allowed. The request must be narrowed by the user and re-planned.

### 3.3 Policy definition constraints

The policy table should be static, backend-owned, immutable, and versioned. It should be validated at application startup. Startup must fail if required policy entries are missing, duplicate, malformed, or inconsistent with the tool catalog.

Do not add a user-editable policy file, environment variable that can enable P2/P3, remote policy fetch, database grant, or provider-driven policy in this phase. Any future policy mutability is a separate Product Owner decision.

## 4. Proposed enforcement pipeline

### Stage 0 — HTTP boundary

Retain current middleware behavior and ordering guarantees:

- Loopback-only bind.
- Host allowlist.
- Origin validation and Origin required for state-changing requests.
- Local token validation on `/api/*`, with exactly one header and constant-time comparison.
- JSON-only state-changing requests.
- 16 KiB maximum request body.
- Existing safe error responses and no token/request-body logging.

The token is only local API authorization. It is not a human identity or confirmation credential.

### Stage 1 — Strict request validation

Validate the external request with strict schemas before policy evaluation:

- Reject extra fields, duplicate/invalid representations where the parser can detect them, wrong types, oversized strings/lists, and out-of-range values.
- Do not accept trusted policy fields or execution-mode overrides from the client.
- Normalize only fields whose normalization rules are explicitly defined and deterministic.
- Preserve the exact user-requested program list and surface uncertainty; do not invent package names or versions.
- Reject arbitrary command text, executable paths, scripts, shell fragments, filesystem paths, or argument vectors as execution directives.

### Stage 2 — Intent and catalog resolution

- Resolve the requested operation to an exact tool ID in the fixed catalog.
- Verify the planner intent and normalized parameters match the tool's declared supported intent.
- Resolve the handler only from the fixed backend-owned mapping.
- Unknown tool IDs, unsupported intents, ambiguous targets, or target mismatch are rejected.
- No reflection, import-by-name, plugin discovery, dynamic module loading, or client-selected callable is permitted.

### Stage 3 — Derive risk and required permission

- Read risk and required permission from backend-owned policy metadata associated with the exact tool/action.
- Independently verify that tool metadata and policy mapping agree.
- In the current catalog, install/remove remain high-impact operations represented only as dry-run previews; they must not gain P3 dispatch.
- If the policy is missing, malformed, or inconsistent, deny. Never default to P0, P1, or a lower risk.

### Stage 4 — Policy decision point

Return a small internal decision object with a closed set of outcomes, for example:

- `ALLOW_DRY_RUN`
- `DENY_PERMISSION_DISABLED`
- `DENY_UNKNOWN_ACTION`
- `DENY_INVALID_PARAMETERS`
- `DENY_POLICY_UNAVAILABLE`
- `DENY_POLICY_MISMATCH`

The decision object is created inside the backend. It is not deserialized from a client/model response. An allow decision must explicitly assert the current `dry_run` mode and P1 scope.

No generic boolean such as client-controlled `approved=true` is sufficient. No policy exception may convert a deny into an allow.

### Stage 5 — Final pre-dispatch guard

Immediately before handler invocation:

- Re-check the exact tool ID, validated parameter object, backend policy version, required permission, and dry-run mode.
- Confirm the resolved handler is the exact fixed handler registered for that tool.
- Confirm no execution-capable handler is registered or reachable in the current catalog.
- If any value is missing or has changed, deny before invocation.

The current stage has no execution confirmation record. P1 plan acknowledgement, if ever added, must not be interpreted as execution authorization. Future execution authorization requires a distinct Phase 6 decision and a separate implementation design.

### Stage 6 — Handler and result boundary

- Invoke only the fixed dry-run/mock handler.
- Handler must be side-effect-free: no OS commands, process creation, filesystem/registry access, package manager, installer, network, or external service.
- Validate the returned object against the strict result schema.
- Reject invalid result types/status values; do not retry through another handler.
- Result text must explicitly state dry-run only and no changes made.
- A handler exception returns a bounded safe error; it must not expose secrets, full request content, or traceback details to the client.

## 5. Fail-closed decision table

| Condition | Required behavior | Handler reachable? |
|---|---|---|
| Unknown tool ID | Reject | No |
| Unknown or unsupported intent | Reject | No |
| Extra or invalid parameter | Reject | No |
| Target differs from validated plan | Reject | No |
| Client supplies risk/permission/approval/handler field | Reject schema | No |
| Policy entry missing | Deny policy unavailable | No |
| Policy/catalog metadata disagree | Deny policy mismatch | No |
| Required permission is P2 or P3 | Deny permission disabled | No |
| Execution mode is not backend-fixed dry-run | Reject | No |
| Policy version is unknown or inconsistent | Deny | No |
| Fixed handler mapping missing or altered | Deny | No |
| Final pre-dispatch revalidation fails | Deny | No |
| Handler raises exception | Safe failure; no alternate dispatch | Handler was entered, but no retry/fallback |
| Handler result violates schema | Reject result; no alternate dispatch | Handler was entered; no retry/fallback |
| Policy initialization/validation fails | Application startup fails closed | No requests served |

The handler-exception and invalid-result rows are distinct from pre-dispatch denial: the handler may already have been entered. Their required control is no fallback, no retry, and no claim of success. Future implementation must prove dry-run handlers are side-effect-free even under exceptions.

## 6. Confirmation integration boundary

P5-503 defines an exact-action contract, but P5-504 must not treat confirmation as a permission bypass.

Current P1 behavior:

- Build and show the exact Installation Plan.
- A user may review or decline it.
- Acknowledgement is informational only; no execution authorization is created.
- No execute endpoint, approval-and-execute control, or P3 state transition exists.

Future execution authorization, if ever proposed, must be separate from P1 review acknowledgement and require all of:

1. Phase 5 design completion and explicit Product Owner closeout.
2. Separate Phase 6 authorization for the named capability.
3. Backend-owned exact-action confirmation and permission state.
4. Atomic one-time consumption and all expiry/replay/revocation controls from P5-503.
5. A separately reviewed implementation task and explicit Product Owner authorization/merge approval.

This list does not grant permission to implement or execute any such capability.

## 7. Error handling and information disclosure

- Use stable, bounded reason codes for expected denials.
- Do not return internal policy objects, stack traces, local paths, environment values, tokens, or secrets.
- Do not log full chat messages, prompts, installation plan content, credentials, or task history.
- Do not add durable audit persistence here; P5-506 must decide whether minimal security events are allowed, what fields are permitted, and retention/access rules.
- Unexpected internal errors fail closed and return a generic response.
- Do not catch a policy error and continue with a default policy or handler.
- Avoid exposing whether a token was close to valid or which secret comparison failed.

## 8. Concurrency and state

The current P1 policy can remain stateless if it only creates and returns a dry-run report. Do not add a persistent grant store or confirmation database as part of P5-504.

If a future design introduces one-time acknowledgement/authorization records:

- P5-503's state machine must be implemented with atomic transitions.
- Two concurrent requests must not consume the same record twice.
- Revocation and expiry must be checked in the same transaction/critical section as consumption.
- Storage failure, lock timeout, or inconsistent state denies.
- Persistence, restart semantics, retention, and access control must be approved through P5-506/P5-508 before implementation.

## 9. Implementation decomposition proposal (not authorized)

After the planning packet is reviewed, a possible bounded implementation split is:

| Candidate task | Scope | Required tests | Gate |
|---|---|---|---|
| P5-504-I1 | Static policy definitions and startup consistency validation | Missing/duplicate/unknown/mismatched policy cases; P2/P3 deny | Separate explicit PO authorization |
| P5-504-I2 | Single backend policy decision point and pre-dispatch guard | Prove every dispatch passes through policy; deny cases never call handler | I1 complete and explicit PO authorization |
| P5-504-I3 | Dry-run-only handler/result hardening | No-side-effect tests, invalid result, exception, no fallback | I2 complete and explicit PO authorization |

These task IDs are placeholders. They must be reconciled with the integrated plan in P5-508. No code or test changes are authorized by this proposal.

## 10. Acceptance criteria for the design

- One centralized backend policy decision point is required before all tool dispatch.
- Risk, permission, mode, and handler identity are backend-owned.
- Only P0/P1 policy outcomes are enabled; current tools are P1 dry-run only.
- P2/P3 are explicit denials.
- Missing, invalid, inconsistent, or unavailable policy fails closed.
- Strict request validation and fixed catalog/handler mapping are preserved.
- Final pre-dispatch revalidation is required.
- No arbitrary command, path, script, executable, dynamic import, or dynamic handler is introduced.
- Current middleware, loopback, local token, Host/Origin, JSON-only, and 16 KiB protections remain intact.
- Handler failures do not trigger retries or fallback dispatch.
- No confirmation acknowledgement is treated as execution authorization.
- No chat/task-history persistence, durable audit store, provider call, credential, external data transfer, machine inspection, or real PC operation is introduced.
- A4 security review and targeted negative/no-side-effect tests are required before any future runtime implementation is accepted.

## 11. Open decisions for Product Owner

1. Approve or revise the proposed single policy decision point and pipeline.
2. Confirm that missing/invalid policy must fail closed at startup or request time according to the failure class described here.
3. Confirm that P2/P3 remain hard denials and cannot be enabled through environment configuration.
4. Confirm that P1 plan acknowledgement remains informational only and creates no execution authority.
5. Confirm the proposed implementation decomposition or defer it to P5-508.

No decision is assumed from silence.
