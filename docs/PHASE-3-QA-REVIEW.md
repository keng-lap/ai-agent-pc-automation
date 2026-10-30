# Phase 3 — A4 QA and Security Acceptance Review

## Review metadata

| Field | Value |
|---|---|
| Review task | MA-005 |
| Reviewer role | A4 — QA / Security Reviewer |
| Review date | 2026-10-30 |
| Repository baseline | `main` — `e6d6a83b51b5b49e23db0fc592fcf35abaa83766` (PR #36 merge) |
| Review type | Independent source/test inspection, merged PR review, task reports, and Product Owner-supplied Windows 11 evidence review |
| Runtime changes | None |
| Test execution by A4 | Not run. Product Owner-supplied Windows 11 test-script output is recorded in this review and `T-308-REPORT.md`. |

## Executive result

**A4 final reassessment (2026-10-30): all eight Phase 3 acceptance criteria are met for the currently approved local/dry-run scope. The Product Owner approved Phase 3 closeout on 2026-10-30 after reviewing this documentation reconciliation.** T-306/T-307 local authorization and duplicate-header regression are merged. T-308 implementation PR #35 and parser correction PR #36 are merged. The backend tool layer remains allowlisted and dry-run-only; the local chat path is deterministic and does not contact an AI provider.

**Original MA-005 finding:** the planner emitted generic steps and did not identify task-specific prerequisites or explain why each was needed. T-303's report also states that the app does not inspect the PC or browse the web. Criterion 1 was therefore not met at the MA-005 baseline.\n\n**T-308 verified status (2026-10-30):** PR #35 adds structured prerequisites for install, removal, development, and general tasks. Each item has a reason, order, dependency references, and one of three knowledge states. PR #36 fixes optional leading `Please` parsing for install/setup requests. A4 inspected the merged planner and tests; the Product Owner supplied a passing Windows 11 full test-script run (100 pytest, Ruff, 21 frontend tests).

**Disposition:** The original criterion 1 gap is closed by the merged T-308 implementation (PR #35) and parser correction (PR #36). The final A4 reassessment above supersedes the earlier MA-005 finding. No acceptance criterion was weakened.

## Acceptance criteria assessment

| # | Criterion | Result | Evidence / finding |
|---|---|---|---|
| 1 | Convert a request into an end-to-end plan that identifies relevant prerequisites and explains why each is needed | MET — T-308 | `planner.py` returns category-specific prerequisite records for install, removal, development, and general tasks. Each record has an ID, order, reason, dependency references, and explicit knowledge status. `test_planner.py` covers categories, Thai/English output, missing targets, dependency ordering, deterministic output, invalid input, and `Please install ExampleTool for me`. Unknown local facts and source research are explicitly marked unavailable rather than fabricated. Product Owner's Windows test run passed. |
| 2 | Tool selection is constrained to a backend allowlist; unknown tools are rejected safely | MET | `tools.py` defines only `software.install` and `software.remove`; strict Pydantic models reject unknown IDs and extra command fields. `test_tools.py` covers unknown tools, arbitrary command payloads, mismatched intent/target, and unsupported tasks. |
| 3 | Proposed commands are validated against backend-owned tools/parameters; raw model text is never passed directly to a shell | MET FOR CURRENT LOCAL MODE | No provider output is accepted: `agent_core.py` runs deterministic local planning; `tools.py` accepts typed tool IDs and targets only. No shell/subprocess execution exists in the reviewed backend. This is not approval for future provider integration. |
| 4 | Machine-changing tools cannot cause real side effects; tests demonstrate mock/dry-run behavior | MET | `execute_tool()` returns a `dry_run` result only. `test_tools.py` asserts dry-run behavior; `test_chat.py` asserts dry-run response. Backend import guard checks for forbidden OS/process/network capabilities. |
| 5 | Backend enforces approved local authorization before Agent processing | MET | `security.py` requires exactly one `X-Local-Agent-Token` on `/api/*` using constant-time comparison; missing, invalid, and duplicate tokens are rejected. T-306/T-307 tests and Windows evidence are recorded in `T-306-REPORT.md`. |
| 6 | Success/failure responses are predictable and do not expose secrets or tracebacks | MET FOR TESTED API PATHS | `test_chat.py` covers validation, deterministic responses, generic internal error, and traceback/detail scrubbing. `test_security.py` covers safe authorization errors and request boundary checks. |
| 7 | Deterministic tests cover validation, planning, tool selection, safety boundaries, and error handling | MET | Test files cover chat, planner, tools, security, configuration, and health. Product Owner's final post-T-307 run reports 100 backend tests, Ruff pass, and 21 frontend tests. |
| 8 | Documentation records provider/data-flow decisions and final behavior; all changes are merged before Phase 4 | MET AFTER THIS DOCS PR MERGES | Existing phase/provider decisions remain explicitly recorded as open or unapproved; T-306/T-307/T-308 behavior and test evidence are documented. This PR reconciles the final T-308 and Phase 3 acceptance evidence. Phase 4 remains blocked until this documentation is merged and the Product Owner separately approves Phase 3 closeout. |

## Security and boundary findings

- Local API authorization is separate from AI-provider authentication.
- The local token is required for Agent API requests; `/health` remains unauthenticated by design.
- Host and Origin restrictions, JSON content type, and the 16 KiB request limit are enforced by middleware.
- The reviewed Agent core does not make provider/network calls and reports `provider_connected: false`.
- The reviewed tool executor returns dry-run previews and performs no file, process, application, software, or settings changes.
- No live provider calls, provider sign-in, external data transfer, or real PC-changing actions are authorized.
- Phase 5 Safety and Permission System remains a hard gate before any real machine-changing execution.

## Recommended follow-up

T-308 was the approved follow-up task (Issue #34; implementation PR #35, parser correction PR #36). The implementation scope was:

1. Define supported task categories and distinguish known facts, unknown facts, and items requiring discovery.
2. For each supported task, return concrete prerequisite items with a short reason, dependency/order, and whether the item is known or requires a separately approved read-only discovery capability.
3. Avoid pretending the current app can inspect installed software or browse sources; without an approved capability, mark these facts unknown and ask the user or present a non-executable research step.
4. Keep proposed commands as structured data validated against backend-owned schemas; never pass free-form text to a shell.
5. Add deterministic tests for representative English and Thai requests, missing/unknown prerequisites, dependency order, unsupported tasks, and the no-side-effect boundary.
6. Keep all machine-changing operations dry-run/mock and do not add provider calls or external data transfer.

The Product Owner approved T-308 scope on 2026-10-30. A4 inspected the merged planner, tool allowlist, Agent core, security middleware, and relevant deterministic tests. The Product Owner supplied the latest Windows 11 test-script result: 100 pytest passed, Ruff passed, and 21 frontend tests passed. A4 did not execute the suite independently; the evidence is attributed to the Product Owner. Following this documentation reconciliation, the Product Owner approved Phase 3 closeout. Phase 4 remains not started and requires its own explicit start approval.

## Review limitations

- A4 reviewed current source files, tests, and merged task reports through GitHub. A4 did not run the test suite; Windows execution evidence is Product Owner-supplied.
- A4 did not run the test suite or execute the Windows app. The 100 backend / Ruff / 21 frontend result is Product Owner-supplied evidence recorded in `T-306-REPORT.md`.
- No GitHub Actions workflow runs or commit statuses were returned for PR #36 by the available lookup; these are not counted as passing checks.
- The review does not certify behavior beyond the code/tests inspected and the Product Owner-supplied Windows run.
- Phase 3 closeout does not authorize Phase 4, provider integration, additional permissions, or real PC actions. Those remain separately gated.
