# Runtime Diagnostics — Implementation Record

## Implemented in this branch

- Authenticated `GET/PUT /api/diagnostics` control; mode is process-local and changes immediately without a restart.
- Diagnostics default to OFF after backend process start.
- Request/workflow correlation: browser HTTP interceptor sends a per-request UUID in `X-Correlation-ID` and a stable per-tab UUID in `X-Workflow-ID`; backend validates or replaces them, echoes both response headers, and stamps both IDs on structured events.
- Browser telemetry: uncaught JavaScript errors and unhandled promise rejections report error type plus line/column-only stack frames; failed API calls report HTTP status. Raw messages, source paths, URLs, and response bodies are excluded.
- Backend telemetry: request status/duration, Gemini generation/schema repair, Catalog outcomes and upstream HTTP status, Manifest outcomes and upstream HTTP status, Publisher verification, proposal staging, Approval challenge, release authorization, and TOTP queue outcomes. Exception details are frame locations and type only.
- Local persistence: structured event rows in a bounded SQLite database (20,000-event cap), separate from Security Audit.
- Storage: database uses the existing platform secure-storage adapter. The diagnostics directory is a dedicated sibling of the configured job-store directory with a `-Diagnostics` suffix.
- Export: authenticated `GET /api/diagnostics/export` returns bounded NDJSON.
- Publishing: `scripts/publish-runtime-diagnostics.ps1` exports through the local protected store, applies a second allowlist, and pushes a unique run bundle to `diagnostics/runtime-logs`. The raw database is never committed.

## Privacy boundary

- No request bodies, user chat text, cookies, authorization headers, TOTP codes, passwords, API keys, or exception messages are written to detailed diagnostics.
- Exception telemetry records exception type and bounded frame locations only.
- Export applies a strict field allowlist: status, duration, route template, method, candidate/version counts, exception type, and stack frame locations.
- Publishing is available from the authenticated UI and starts asynchronously; switching Diagnostics OFF also triggers one publish after detailed capture stops. No upload occurs per event.
- Publish status exposes only a bounded state, Run ID, safe error category, and the validated GitHub run URL. Failed publishes can be retried from the UI; source events remain in the bounded local SQLite store until retention eviction.
- Basic application error logging and Security Audit are not gated by Diagnostics mode.

## Safety boundary

Diagnostics is observability only. It does not enable or alter Approval, TOTP, Publisher verification, WinGet source validation, Real Install release authorization, or Worker execution. No installer is invoked by these changes.

## Remaining validation

- CI passed on commit `4924d0327a121c8f2c5f90e50c184c0c90fc16ea`: CI, Windows Process Containment, Windows Authenticator DPAPI, Windows Generic Publisher Trust, Windows Real Install Frontend, and AI PR Diff Trigger.
- Windows Process Containment passed 223 tests (7 skipped); this includes the protected diagnostics SQLite persistence test and publisher script parser/lint checks.
- Verify the secure diagnostics SQLite directory and live ON/OFF behavior on the nominated Windows 11 Home target.
- Run one browser Manifest failure with Diagnostics ON, then OFF; publish the sanitized event chain and verify basic errors and Security Audit remain active.
- Confirm no secrets appear in the published JSONL.

## Operator commands

From the repository root, after the application has been run with Diagnostics enabled and at least one event recorded:

```powershell
.`scripts\publish-runtime-diagnostics.ps1`
```

The script requires the project `.venv`, Git authentication for `origin`, and the `diagnostics/runtime-logs` branch. It does not modify the source checkout.
