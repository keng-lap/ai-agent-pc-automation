# Phase 3 — A4 QA and Security Acceptance Review

## Review metadata

| Field | Value |
|---|---|
| Review task | MA-005 |
| Reviewer role | A4 — QA / Security Reviewer |
| Review date | 2026-10-30 |
| Repository baseline | `main` — `0aea6b77bef55f07e32611c814781ef575c0c065` |
| Review type | Source, tests, task reports, and Product Owner-supplied Windows 11 evidence review |
| Runtime changes | None |
| Test execution by A4 | Not run; this is a source/evidence review. Product Owner's final Windows 11 test run is recorded in T-306 report. |

## Executive result

**Phase 3 closeout is not recommended yet.** T-306 local API authorization and T-307 duplicate-header regression are merged and verified. The backend tool layer is allowlisted and dry-run-only. The local chat path is deterministic and does not contact an AI provider.

**One substantive acceptance gap remains:** the first Phase 3 acceptance criterion requires an end-to-end plan that identifies relevant prerequisites and explains why each is needed. The current planner emits a fixed set of generic steps; it does not identify task-specific prerequisites, verify installed software, or explain why each concrete prerequisite is necessary. T-303's report explicitly acknowledges that prerequisite discovery and source research are not implemented. Criterion 1 is therefore not met.

Phase 3 should remain open until a bounded follow-up task closes this gap or the Product Owner explicitly changes the acceptance criterion through the project's decision process. Do not silently weaken the criterion.

## Acceptance criteria assessment

| # | Criterion | Result | Evidence / finding |
|---|---|---|---|
| 1 | Convert a request into an end-to-end plan that identifies relevant prerequisites and explains why each is needed | NOT MET | `planner.py` returns six fixed generic stages. It does not identify task-specific prerequisites or justify concrete items. `T-303-REPORT.md` says it does not inspect the PC, browse the web, or identify installed software. |
| 2 | Tool selection is constrained to a backend allowlist; unknown tools are rejected safely | MET | `tools.py` defines only `software.install` and `software.remove`; strict Pydantic models reject unknown IDs and extra command fields. `test_tools.py` covers unknown tools, arbitrary command payloads, mismatched intent/target, and unsupported tasks. |
| 3 | Proposed commands are validated against backend-owned tools/parameters; raw model text is never passed directly to a shell | MET FOR CURRENT LOCAL MODE | No provider output is accepted: `agent_core.py` runs deterministic local planning; `tools.py` accepts typed tool IDs and targets only. No shell/subprocess execution exists in the reviewed backend. This is not approval for future provider integration. |
| 4 | Machine-changing tools cannot cause real side effects; tests demonstrate mock/dry-run behavior | MET | `execute_tool()` returns a `dry_run` result only. `test_tools.py` asserts dry-run behavior; `test_chat.py` asserts dry-run response. Backend import guard checks for forbidden OS/process/network capabilities. |
| 5 | Backend enforces approved local authorization before Agent processing | MET | `security.py` requires exactly one `X-Local-Agent-Token` on `/api/*` using constant-time comparison; missing, invalid, and duplicate tokens are rejected. T-306/T-307 tests and Windows evidence are recorded in `T-306-REPORT.md`. |
| 6 | Success/failure responses are predictable and do not expose secrets or tracebacks | MET FOR TESTED API PATHS | `test_chat.py` covers validation, deterministic responses, generic internal error, and traceback/detail scrubbing. `test_security.py` covers safe authorization errors and request boundary checks. |
| 7 | Deterministic tests cover validation, planning, tool selection, safety boundaries, and error handling | MET | Test files cover chat, planner, tools, security, configuration, and health. Product Owner's final post-T-307 run reports 100 backend tests, Ruff pass, and 21 frontend tests. |
| 8 | Documentation records provider/data-flow decisions and final behavior; all changes are merged before Phase 4 | PARTIALLY MET | Current docs correctly state that provider choice, data transfer, model/fallback, and token storage remain open and that no provider call is authorized. T-306/T-307 docs are merged. Phase 3 closeout documentation remains incomplete until criterion 1 is resolved. |

## Security and boundary findings

- Local API authorization is separate from AI-provider authentication.
- The local token is required for Agent API requests; `/health` remains unauthenticated by design.
- Host and Origin restrictions, JSON content type, and the 16 KiB request limit are enforced by middleware.
- The reviewed Agent core does not make provider/network calls and reports `provider_connected: false`.
- The reviewed tool executor returns dry-run previews and performs no file, process, application, software, or settings changes.
- No live provider calls, provider sign-in, external data transfer, or real PC-changing actions are authorized.
- Phase 5 Safety and Permission System remains a hard gate before any real machine-changing execution.

## Recommended follow-up

Create a separately scoped Phase 3 follow-up task to implement and test task-specific prerequisite planning. At minimum, it should:

1. Define supported task categories and distinguish known facts, unknown facts, and items requiring discovery.
2. For each supported task, return concrete prerequisite items with a short reason, dependency/order, and whether the item is known or requires a separately approved read-only discovery capability.
3. Avoid pretending the current app can inspect installed software or browse sources; without an approved capability, mark these facts unknown and ask the user or present a non-executable research step.
4. Keep proposed commands as structured data validated against backend-owned schemas; never pass free-form text to a shell.
5. Add deterministic tests for representative English and Thai requests, missing/unknown prerequisites, dependency order, unsupported tasks, and the no-side-effect boundary.
6. Keep all machine-changing operations dry-run/mock and do not add provider calls or external data transfer.

A4 recommends that A1 prepare this task for Product Owner review. Do not start implementation until the Product Owner approves its scope. After implementation, A4 should rerun relevant tests and reassess criterion 1.

## Review limitations

- A4 reviewed current source files, tests, and merged task reports through GitHub.
- A4 did not run the test suite or execute the Windows app. The 100 backend / Ruff / 21 frontend result is Product Owner-supplied evidence recorded in `T-306-REPORT.md`.
- This review does not certify untested runtime behavior beyond the code/tests inspected.
- This review does not authorize Phase 4, provider integration, additional permissions, or real PC actions.
