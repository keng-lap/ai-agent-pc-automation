# T-402 — Backend Tool Layer Gap Analysis

## Review basis
Read-only review of current main source:
- src/backend/agent_backend/tools.py
- src/backend/agent_backend/agent_core.py
- src/backend/agent_backend/planner.py
- tests/backend/test_tools.py
- tests/backend/test_chat.py

No source code was changed and no runtime tests were run as part of this analysis.

## What already exists

### Tool request/result
- ToolId is a Literal allowlist containing software.install and software.remove.
- ToolStatus is limited to dry_run.
- ToolRequest uses Pydantic strict/frozen configuration, forbids extra fields, and bounds target length to 1–120.
- ToolResult is strict/frozen, carries status=dry_run and approval_required=true, and bounds summary.

### Selection and validation
- _ALLOWED_INTENTS maps each ToolId to its corresponding planner intent.
- select_tool() chooses only a mapped tool and requires a target.
- validate_tool_request() checks intent category and case-insensitive target equality.
- Unknown/non-software intents fail selection with ValueError.

### Execution boundary
- execute_tool() returns a deterministic preview and does not invoke OS APIs, processes, shells, installers, or network clients.
- agent_core.run_agent() composes planner, selection, validation, and dry-run handler.
- Provider connection is explicitly false. No provider call is made.

### Tests
- Tests cover allowlisted selection for install/remove.
- Tests reject unknown tool IDs and arbitrary extra command fields.
- Tests reject intent/target mismatch.
- Tests assert dry-run status and no-change summary.
- Chat tests assert local deterministic planning, dry-run behavior, and forbidden capability imports.

## Gaps relative to Phase 4 proposal

| Area | Current state | Gap / recommendation | Risk |
|---|---|---|---|
| Tool catalog | Allowlist mapping only | Formal metadata (description, risk, mode, schemas, approval flag) is not represented as one catalog contract | Low if descriptive only |
| Registry | _ALLOWED_INTENTS is current map | Decide whether registry abstraction adds value; avoid refactoring for pattern purity | Medium |
| Dispatch | select -> validate -> execute direct composition | A narrow dispatcher could make handler lookup explicit, but must not accept arbitrary callables or user-provided names | High if overly dynamic |
| Result validation | ToolResult constructed by handler | Consider validating output at dispatch boundary if catalog becomes extensible | Low |
| Task lifecycle | TaskPlan and ToolResult exist; no unified task state model | T-403 should define request-scoped status separately from tool execution result | Medium |
| Persistence | No task history mechanism in reviewed files | Keep it that way; D-API-2 forbids chat/history persistence | High |
| Error representation | ValueError caught in agent_core and yields no tool result | Typed UI-safe reason/status may improve UX; avoid exposing internals | Medium |
| Frontend mapping | AgentResponse exposes plan and optional tool_result | Verify frontend mapping and current UI state before adapter changes | Medium |

## Recommended implementation approach (not authorization to code)
1. Keep ToolRequest and ToolResult constraints unless a demonstrated requirement needs change.
2. Add metadata around the existing allowlist rather than create a plugin architecture.
3. If a registry is introduced, make it static, backend-owned, immutable, and closed by default.
4. Use an explicit mapping from allowlisted ToolId to fixed handler functions. Never resolve handlers dynamically from request data.
5. Keep selection and intent/target checks; centralize only if tests prove behavior is preserved.
6. Keep execution_mode dry_run and reject any other mode at the execution boundary.
7. Define task status as orchestration/UI concept, not a persisted job system.
8. Add focused tests before refactoring.

## Dependencies and implementation gates
- T-402 depends on reviewed/stable T-401 contract.
- T-403 must define lifecycle and response mapping before frontend integration.
- T-404 depends on stable T-402/T-403 response fields.
- A4 reviews dispatch abstraction for dynamic invocation, import paths, and side effects.
- This analysis alone does not authorize code implementation; implementation scope must be separately approved.

## Items needing source verification before implementation
- Inspect actual frontend components and API service mapping.
- Inspect chat/API response models for backwards compatibility.
- Run full scripts/test.ps1 on Windows 11 after code changes.
- Confirm no new imports or APIs cross the backend safety boundary.
