# T-403 — Request-Scoped Task Lifecycle Contract

## Status
Contract proposal only. It defines a lightweight in-memory lifecycle for one request. It does not create a queue, persistent task record, background worker, or real execution state.

## Goals
- Give frontend and backend a shared vocabulary for one request.
- Keep task lifecycle distinct from ToolResult.status.
- Make invalid transitions fail closed.
- Ensure client input cannot forge backend-owned state.
- Preserve D-API-2: no chat messages/history or task history persistence.

## Proposed states
| State | Meaning | Terminal |
|---|---|---|
| planned | Planner produced a bounded task plan | No |
| validation_failed | Tool request failed schema, allowlist, intent, or target validation | Yes |
| awaiting_user_confirmation | Required clarification/approval is outstanding; no action is authorized | No |
| dry_run_completed | Registered dry-run handler returned a preview and made no changes | Yes |
| failed | Controlled unexpected failure occurred; no action is reported as completed | Yes |

No queued, running, cancelled, completed-real, or executed state is included in Phase 4. A future asynchronous lifecycle needs a separate proposal.

## Allowed transitions
| From | To | Condition |
|---|---|---|
| planned | validation_failed | Backend validation rejects the proposed tool request |
| planned | awaiting_user_confirmation | Required user input/confirmation is outstanding |
| planned | dry_run_completed | Valid allowlisted request is handled in dry-run mode |
| planned | failed | Controlled unexpected failure occurs |
| awaiting_user_confirmation | planned | User supplies clarification and a new request is evaluated; do not mutate an old task record |
| awaiting_user_confirmation | validation_failed | Re-evaluation rejects the clarified request |

Terminal states have no outgoing transitions. A new user message creates a new request lifecycle; it does not reopen or mutate a previous request.

## Ownership and API contract
- State is generated and owned by the backend.
- Client may display state but cannot submit or override it.
- State derives from actual orchestration events, not frontend inference.
- ToolResult.status remains dry_run and is not replaced by task state.
- If Phase 4 adds task_status to AgentResponse, it must be typed, server-generated, documented, and covered by API compatibility tests.
- Do not expose internal exception strings. Use bounded, user-safe reason codes/messages.
- Do not add an endpoint to set arbitrary state.

## Lifetime and privacy
- State exists only while processing a single request and in the response.
- No database, file, browser storage, local storage, analytics, or background queue.
- No request body, user message, task plan, or task result is retained as history.
- Existing language preference persistence remains unchanged and is the only permitted preference persistence under D-API-2.

## UI mapping
- planned: show plan.
- validation_failed: show a safe validation message; no executable tool preview.
- awaiting_user_confirmation: show what information/approval is missing; no machine action.
- dry_run_completed: show dry-run preview and explicit “no changes made”.
- failed: show generic safe failure status; do not leak stack traces or internal detail.

## Acceptance criteria
1. Backend state is typed and server-owned.
2. Only transitions in the table are possible.
3. Terminal states cannot transition.
4. Client cannot forge lifecycle state.
5. Task lifecycle and ToolResult.status remain separate.
6. State is request-scoped and not persisted.
7. No real execution state exists in Phase 4.
8. API/UI tests cover every valid and invalid transition and all display states.

## Open issue for implementation
Current AgentResponse does not expose a unified task_status field. T-402 must decide whether adding one is necessary and maintain backwards compatibility. T-403 implementation must not proceed until the exact API representation and frontend impact are reviewed.
