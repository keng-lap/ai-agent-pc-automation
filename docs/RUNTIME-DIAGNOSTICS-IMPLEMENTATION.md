# Runtime Diagnostics — Implementation Record

## Implemented in this branch

- Authenticated `GET/PUT /api/diagnostics` control; mode is process-local and changes immediately without a restart.
- Diagnostics default to OFF after backend process start.
- Request correlation: browser HTTP interceptor sends a UUID in `X-Correlation-ID`; backend validates or replaces it and echoes it in the response header.
- Browser telemetry: uncaught JavaScript errors, unhandled promise rejections, and failed API calls are reported using fixed event codes and HTTP status only.
- Backend telemetry: request status/duration, unexpected exception frame locations, Catalog outcomes, Manifest outcomes, and sanitized exception frame locations.
- Local persistence: structured event rows in a bounded SQLite database (20,000-event cap), separate from Security Audit.
- Storage: database uses the existing platform secure-storage adapter. The diagnostics directory is a dedicated sibling of the configured job-store directory with a `-Diagnostics` suffix.
- Export: authenticated `GET /api/diagnostics/export` returns bounded NDJSON.
- Publishing: `scripts/publish-runtime-diagnostics.ps1` exports through the local protected store, applies a second allowlist, and pushes a unique run bundle to `diagnostics/runtime-logs`. The raw database is never committed.

## Privacy boundary

- No request bodies, user chat text, cookies, authorization headers, TOTP codes, passwords, API keys, or exception messages are written to detailed diagnostics.
- Exception telemetry records exception type and bounded frame locations only.
- Export applies a strict field allowlist: status, duration, route template, method, candidate/version counts, exception type, and stack frame locations.
- Publishing is explicit; no automatic GitHub upload occurs.
- Basic application error logging and Security Audit are not gated by Diagnostics mode.

## Safety boundary

Diagnostics is observability only. It does not enable or alter Approval, TOTP, Publisher verification, WinGet source validation, Real Install release authorization, or Worker execution. No installer is invoked by these changes.

## Remaining validation

- CI and CodeRabbit review results must be checked against the latest PR head.
- Verify the Windows secure diagnostics SQLite directory on the nominated Windows 11 Home target.
- Run one browser Manifest failure with Diagnostics ON, then OFF; inspect the exported/published event chain and verify basic errors and Security Audit remain active.
- Confirm no secrets appear in the published JSONL.

## Operator commands

From the repository root, after the application has been run with Diagnostics enabled and at least one event recorded:

```powershell
.`scripts\publish-runtime-diagnostics.ps1`
```

The script requires the project `.venv`, Git authentication for `origin`, and the `diagnostics/runtime-logs` branch. It does not modify the source checkout.
