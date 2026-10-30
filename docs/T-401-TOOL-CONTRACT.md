# T-401 — Tool Contract and Catalog

## Status
Contract proposal for Phase 4. It formalizes the two existing dry-run tools only. It adds no tool and authorizes no real execution.

## Design principles
1. Backend owns tool identifiers, schemas, validation, risk metadata, and dispatch.
2. A planner intent is not permission to execute.
3. Client/model tool identifiers are untrusted until backend allowlist validation.
4. Unknown tools, extra fields, invalid types, oversized values, and intent/target mismatches fail closed.
5. Handlers return typed results. No arbitrary command, executable path, shell arguments, or script body is accepted.
6. Machine-changing operations remain dry-run/mock until Phase 5 is complete and explicitly approved.
7. No provider calls, PC discovery, external network, credentials, or persistent task/chat history.

## Current catalog (no capability expansion)

| Tool ID | Purpose | Input | Output | Risk class | Execution mode | Approval |
|---|---|---|---|---|---|---|
| software.install | Preview a requested software installation | ToolRequest: tool_id, target | ToolResult: tool_id, target, status, approval_required, summary | High — machine-changing if ever executed | dry_run only | approval_required=true; no real execution path |
| software.remove | Preview a requested software removal | ToolRequest: tool_id, target | ToolResult: tool_id, target, status, approval_required, summary | High — machine-changing if ever executed | dry_run only | approval_required=true; no real execution path |

The current Python definitions in src/backend/agent_backend/tools.py are authoritative for field constraints. ToolRequest is strict, frozen, rejects extra fields, and bounds target length to 1–120 characters. ToolResult is strict/frozen, status is dry_run, approval_required is literal true, and summary is bounded.

## Proposed catalog metadata contract
Metadata is descriptive and backend-owned; it must not be accepted as executable input.

| Field | Type / rule | Meaning |
|---|---|---|
| id | stable unique allowlisted string | Exact tool identifier |
| display_name | localized text or translation key | Human-readable label |
| description | bounded text | Intended purpose |
| supported_intents | backend-owned intent IDs | Planner categories supported |
| input_schema | backend-owned typed schema reference | Accepted request structure |
| output_schema | backend-owned typed result reference | Result structure |
| risk_class | low, medium, high, critical | Consequence if real execution were ever enabled |
| execution_mode | mock, dry_run, real | Current value for both entries is dry_run |
| approval_required | boolean | True for both current tools |
| enabled | server-side boolean | Selection availability; not a permission grant |

The value real is reserved descriptive vocabulary only. This phase does not implement or permit it. A future tool cannot become real by changing metadata alone.

## Request/response contract

### ToolRequest
- tool_id: exactly one allowlisted ToolId.
- target: non-empty string, 1–120 characters.
- Extra fields forbidden.
- Strict type validation; immutable model.
- No command, shell, path, URL, flags, environment variables, credentials, or arbitrary parameters.

### ToolResult
- tool_id: allowlisted ToolId.
- target: validated target.
- status: dry_run.
- approval_required: true.
- summary: bounded explanation that no changes were made.

### Validation sequence
1. Parse with strict schema and reject extra fields.
2. Resolve tool ID from backend-owned catalog.
3. Validate planner intent against supported intents.
4. Validate target matches planner-owned target.
5. Require execution mode dry_run/mock; reject unapproved real mode.
6. Invoke only the registered deterministic handler.
7. Validate handler output against declared schema.
8. Return preview. Do not mutate the machine.

## Task lifecycle input to T-403
Proposed request-scoped states:
- planned
- validation_failed
- awaiting_user_confirmation
- dry_run_completed
- failed

The lifecycle must not imply real execution. No queued/running/real-completed state is required in Phase 4. Keep state in memory for one request only; do not write a database, file, chat history, or task history. T-403 owns final naming and transitions.

## Acceptance criteria
- Catalog lists only software.install and software.remove.
- Both are high risk and dry_run only.
- Schemas are backend-owned and strict; arbitrary commands are not representable.
- Intent and target validation remain mandatory.
- Handler resolution is allowlisted and deterministic.
- Every result explicitly states dry_run and approval_required.
- Metadata changes alone cannot enable real execution.
- Tests cover unknown IDs, extra fields, wrong types, invalid target, intent mismatch, and no side effects.

## Decisions intentionally not made
- Python constants vs typed catalog objects.
- Exact localization structure.
- New module vs enriching tools.py.
- Future read-only tools or real execution.
These require separate proposals and review.
