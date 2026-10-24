# Phase 3 — Agent Core

## Status

**Proposed for Product Owner review.** Phase 3 implementation has not started. This document defines the scope and sequence for starting it safely; it does not approve an AI provider, external data transfer, or real machine-changing actions.

## Goal

Turn a chat request into an understandable plan, select an allowed tool, execute it through a controlled interface, and report success or failure. Phase 3 builds the Agent core while keeping machine-changing tools in mock or dry-run mode.

## Approved constraints

- Preserve the phase order in `ROADMAP.md` (P-ORDER-1, option A).
- Bind local services to loopback only (P-SEC-1 / D-SEC-5).
- Tools that can modify the computer must use mock or dry-run behavior until Phase 5's Safety and Permission System is implemented and approved.
- Phase 2's decision D-SEC-1 requires a local-authorization decision before Phase 3 enables any Agent capability. Phase 3 must define and enforce that boundary before enabling Agent processing through the application.
- Never treat model output as authorization. The backend owns validation and enforcement.
- Keep deterministic behavior testable without contacting a live AI provider.

## In scope

1. Define the request, plan, tool-call, result, and error contracts.
2. Analyze a request and produce a structured intent and plan.
3. Select tools only from a backend-controlled allowlist.
4. Execute read-only tools, if approved for the task, and mock/dry-run implementations for machine-changing tools.
5. Return a user-readable result and safe, non-sensitive errors.
6. Add deterministic tests for validation, planning, tool selection, execution boundaries, and failures.

## Out of scope

- Real execution of actions that change files, processes, applications, software, or system settings.
- Choosing or integrating an external AI provider, sending user text to a remote service, or adding provider credentials before the Product Owner decides the provider, privacy/data-flow policy, and secret-storage approach.
- Implementing Phase 5's full permission, confirmation, and audit system early under another name.
- Making the Agent available to non-loopback clients.

## Decisions required before provider-backed Agent behavior

| Decision | Required answer |
|---|---|
| AI provider and model | Provider/model, or an explicit decision to begin with a deterministic local/mock implementation. |
| Data handling | Whether user messages may leave the computer, what data may be sent, and required retention/privacy constraints. |
| Credentials | Where credentials are stored and how they are supplied; never commit secrets or put them in frontend code. |
| Local authorization (D-SEC-1) | What user action authorizes Agent processing in the local application and how the backend enforces it. |
| Phase 3 tool boundary | Which read-only tools, if any, are approved; all machine-changing tools remain mock/dry-run. |

Until these decisions are recorded in the relevant approved phase documents, use only deterministic local/mock behavior and do not make external provider calls.

## Proposed task sequence

| Task | Deliverable | Gate |
|---|---|---|
| T-301 | Approve this Phase 3 scope, decisions, and safety boundary. | Product Owner review and merge. |
| T-302 | Define Agent request/response, plan, tool, result, and error contracts; define local authorization behavior. | T-301 merged; authorization decision recorded. |
| T-303 | Implement deterministic intent analysis and plan generation with validation and tests. | T-302 approved. |
| T-304 | Implement allowlisted tool selection and mock/dry-run execution with boundary tests. | T-302 approved; no machine-changing side effects. |
| T-305 | Connect the Agent Core to the chat endpoint and report results/errors. | T-303 and T-304 complete; provider decision followed if applicable. |

Tasks should be delivered in separate reviewable branches/PRs using `<type>/<task-id>-<short-name>`. Do not begin a gated task until its stated prerequisite is merged and any required decision is recorded.

## Acceptance criteria for Phase 3

- A request is validated and converted into a structured intent and plan.
- Tool selection is constrained to a backend allowlist and invalid/unknown tools are rejected safely.
- Machine-changing tools cannot cause real side effects; tests demonstrate mock/dry-run behavior.
- The backend enforces the approved local-authorization boundary before processing Agent capabilities.
- Success and failure responses are predictable, useful, and do not expose secrets or internal tracebacks.
- Deterministic tests cover request validation, planning, tool selection, safety boundaries, and error handling.
- Documentation records provider/data-flow decisions and the final behavior; all changes are merged to GitHub before Phase 4 starts.

## Verification

This is a documentation-only proposal. No implementation or tests are included in this change. Each implementation task must run its relevant checks and report the results in its PR.

## References

- `docs/ROADMAP.md` — Phase 3 scope and P-ORDER-1 constraint.
- `docs/PROPOSALS.md` — P-SEC-1, P-SEC-2, P-SEC-3, P-SEC-4, P-ORDER-1, and the open AI provider item.
- `docs/PHASE-2.md` — approved Phase 2 decisions, including D-SEC-1.
