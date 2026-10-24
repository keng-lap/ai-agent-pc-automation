# T-304 Completion Report

## Status

Implementation complete on `feat/t-304-allowlisted-tools`; awaiting review and merge. T-304 builds on T-303 (merged in PR #24).

## Delivered

- Added a backend-owned allowlist for `software.install` and `software.remove`.
- Tool requests use a strict schema with a structured target. Unknown tool IDs and extra fields (including command text) are rejected.
- Tool proposals must match the planner's intent category and target.
- Tool selection and execution are deterministic and local. Execution returns a dry-run preview and always requires approval; it performs no machine changes.
- Added tests for allowlist selection, unsupported tasks, unknown tools, arbitrary command rejection, target/category mismatch, and dry-run results.
- Updated Phase 3 status documentation to record T-303 as merged and T-304 as complete pending this PR.

## Safety boundary

No subprocess, shell, network, filesystem, provider, or operating-system action is invoked by this tool layer. It is not connected to the chat endpoint. Real tool execution remains out of scope until the later safety phase is implemented and approved.

## Verification

Run from `src/backend`:

```powershell
python -m pytest ../../tests/backend
python -m ruff check agent_backend/tools.py ../../tests/backend/test_tools.py
```

Results from `src/backend`:

- `python -m pytest ../../tests/backend -q` — 95 passed.
- `python -m ruff check agent_backend/tools.py ../../tests/backend/test_tools.py` — passed.
