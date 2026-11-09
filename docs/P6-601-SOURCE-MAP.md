# P6-601 — Read-only Backend Source Map

## Scope and evidence

Read-only review of the Phase 6 foundation branch. No runtime files were changed, no package manager was invoked, and no Windows machine was inspected or modified. This map records the current source structure; it is not a security approval for real execution.

## Current request and tool flow

| Concern | Source | Observed responsibility / boundary |
|---|---|---|
| App composition | `src/backend/agent_backend/main.py` | Creates FastAPI app, validates static policy at startup, installs local web security middleware, and mounts auth/chat/plan routers. Chat and plan routers use the session dependency. |
| Browser/API boundary | `src/backend/agent_backend/security.py` | Restricts Host and Origin to loopback values, requires the local Agent token on `/api/*`, requires JSON + Origin for state-changing requests, and caps request bodies at 16 KiB. |
| Authentication services | `src/backend/agent_backend/auth_api.py` | Builds Google OIDC Master User allowlist/session services, DPAPI-protected TOTP secret storage, enrollment manager, replay guard, and step-up challenge store. |
| Session identity | `auth_api.py` (`require_session`) | Resolves the session cookie and attaches the authenticated principal to request state when auth is configured. |
| Intent and plan API | `src/backend/agent_backend/plan_api.py` | Creates deterministic typed plans from user request; exposes plan read, step-up challenge, and approval routes. No package search or machine operation occurs. |
| Immutable plan | `src/backend/agent_backend/plans.py` | Strict frozen plan models; 10-minute expiry; process-local store capped at 128; SHA-256 digest binds material plan content; source/dependency/live checks remain explicitly NOT_CHECKED/false. |
| Tool catalog and dispatch | `src/backend/agent_backend/tools.py` | Fixed catalog contains only `software.install` and `software.remove`; strict request schema rejects extra fields; fixed handler map returns dry-run previews only. No shell, subprocess, installer, package manager, or download handler exists here. |
| Policy decision | `src/backend/agent_backend/policy.py` | Backend-owned R0–R3 to P0–P3 matrix; current tool IDs map only to R1/P1/dry_run. R2/P2 and R3/P3 deny. Catalog/policy mismatch fails startup or request validation. |
| Exact-action step-up | `src/backend/agent_backend/step_up.py` and `plan_api.py` | Challenge binds owner, session, plan ID, action digest, and high-risk classification; challenge TTL is 120 seconds; attempts/capacity are bounded and TOTP replay guard is used. `plan_api.py` calls `create` and `verify_and_consume` before the existing dry-run dispatch. |
| Security audit | `src/backend/agent_backend/audit.py` | Bounded in-memory allowlisted metadata only; no prompts/secrets/raw parameters; max 500 events. Current `record_optional_audit_event` is explicitly best-effort and does not fail the request when recording fails. |

## Confirmed current behavior

- `software.install` and `software.remove` are the only registered tool IDs and both are dry-run only.
- The plan API currently labels source as not checked and sets `live_checks_performed=false`; there is no trusted software source-discovery service or package-manager adapter in the inspected flow.
- Approval of an existing plan verifies a short-lived TOTP challenge bound to the plan digest and then invokes only the fixed dry-run handler.
- The approval response explicitly states `DRY_RUN_ONLY_NO_CHANGES_MADE`.
- Plan and step-up state are process-local; audit events are also process-local and optional diagnostics.
- There is no current runtime support for WinGet, Chocolatey, npm package discovery, installer download, signature inspection, or real software installation.

## A4 review items / gaps to resolve before any side-effecting capability

1. **F-516-01 remains a hard gate.** Independently review the merged Google OIDC + DPAPI/TOTP implementation, exact-action binding, user-presence enforcement, bypass resistance, expiry, replay, and fail-closed behavior. Phase 5 residual acceptance is not an A4 pass.
2. **Audit semantics differ from a mandatory security ledger.** The current audit API is optional and fail-open. A future side-effecting handler must not assume this sink provides durable or fail-closed evidence; define a separately approved mandatory audit design before execution.
3. **Step-up module documentation is stale/inconsistent.** The module docstring in `step_up.py` says it is not wired to the existing P1 dry-run route, while current `auth_api.py` builds the store and `plan_api.py` calls it. A4 should verify the actual route wiring and update the misleading module documentation in a separately reviewed change.
4. **Approval cache/idempotency semantics need explicit review.** `plan_api.py` checks the in-memory approval-result cache before re-verifying a new challenge. A4 should confirm the intended same-session/idempotent behavior, ownership binding, expiry, and replay implications before a real side-effect path is designed.
5. **No software provenance data exists in current plans.** `ProgramPlan.source` defaults to not checked and source verification is fixed to NOT_CHECKED. Trusted discovery must add a separate typed evidence contract; it must not treat the existing free-text `target` as a package ID or command.
6. **No package-manager execution path exists.** Future adapters must be fixed backend-owned handlers with strict typed package identity/source/version fields; never accept a free-form command, URL, executable path, script, or model-supplied handler.

## Next bounded work

Complete the remaining P6-601 threat model and A4 review, including the items above. Then propose a separate planning/design task for a read-only trusted software discovery contract (WinGet primary, Chocolatey secondary, npm for Node.js packages) before proposing any runtime installer capability. No installation capability is authorized by this source map.