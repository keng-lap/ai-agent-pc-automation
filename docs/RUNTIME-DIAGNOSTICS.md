# Runtime Diagnostics

## Status

Implementation scope for the browser-operated local application. This work is isolated on
`feat/runtime-diagnostics`; it does not change the P6-609 Real Install authorization or execution
boundary.

## Goals

- Let the signed-in operator enable or disable detailed diagnostics immediately, without restarting
  the frontend or backend.
- Correlate a browser action with its backend request and backend workflow events using a
  request/correlation ID.
- Capture browser runtime errors, failed API requests, backend exceptions, and bounded workflow
  stage events.
- Preserve a basic operational error log and Security Audit when detailed diagnostics are OFF.
- Make sanitized diagnostic runs publishable to a dedicated Git branch for maintainer analysis,
  without requiring screenshots or log-file uploads in chat.

## Diagnostic mode contract

- Default state is OFF after process start unless a later approved persistence design says otherwise.
- Toggle is runtime-only and takes effect on the next event/request; no restart is required.
- OFF suppresses detailed diagnostic events and stack traces. It does not disable existing
  application/security logs, audit records, or safe error responses.
- ON enables detailed events with a timestamp, severity, component, stage, event code, correlation
  ID, duration/status where applicable, and a sanitized exception stack.
- Diagnostic mode is not an authorization capability and cannot enable, weaken, or bypass Approval,
  TOTP, Publisher verification, WinGet source validation, or Real Install controls.

## Required event coverage

1. Browser: uncaught errors, unhandled promise rejections, API request failures, HTTP status,
   elapsed time, and request/correlation ID.
2. Backend/API: request start/end, status, duration, validation failures, handled API failures,
   and unexpected exceptions with stack traces.
3. Workflow: catalog lookup, manifest discovery/validation, publisher verification, install
   readiness/proposal, approval challenge, TOTP approval, queueing, and worker execution stages.
4. External dependencies: bounded HTTP status/timeout/retry outcomes for GitHub/WinGet metadata and
   Gemini provider calls. Never record request/response bodies by default.

## Privacy and security

- Never record local-agent tokens, cookies, authorization headers, TOTP codes, passwords, API keys,
  OAuth codes/tokens, installer secrets, or raw request bodies.
- Sanitize URLs and exception text before persistence; avoid query strings and user-provided message
  content unless explicitly allowlisted.
- Bound event size and retention; use structured JSON Lines.
- The browser must not be able to submit arbitrary log content to an unauthenticated endpoint.
- Diagnostic read/toggle endpoints must require the existing authenticated local session and local
  Agent security boundary.
- Diagnostic mode must not expose stack traces to the browser response; detailed traces stay in
  local diagnostic logs.
- Publishing is available through an authenticated UI action and is also triggered asynchronously when Diagnostics is switched OFF. Sanitize again before pushing to a dedicated branch;
  never auto-publish on every event.

## Log destinations and publishing

- Keep local runtime diagnostic logs separate from Security Audit and basic operational error logs.
- Use a dedicated branch, `diagnostics/runtime-logs`, for sanitized run bundles.
- A publisher script should create a unique run folder containing a summary and sanitized JSONL
  files, verify the target branch, and push without modifying the source checkout.
- Publishing must report the exact commit/run path and fail closed if sanitization or push fails.
- Do not commit raw local logs or secrets.

## Acceptance criteria

- Toggle ON/OFF works immediately without restart and is protected by existing authentication.
- With mode OFF, basic errors and Security Audit continue while detailed events/stack traces stop.
- With mode ON, one failed Manifest lookup can be traced end-to-end by a single correlation ID,
  including the exact failing stage and safe upstream status/error code.
- Browser and backend events share the same correlation ID for each API request.
- Secret-redaction tests cover headers, cookies, query strings, exception text, and structured fields.
- Tests prove diagnostic mode cannot affect Real Install, Approval, TOTP, Publisher verification,
  or WinGet source trust decisions.
- Logs can be published from the UI to `diagnostics/runtime-logs`, automatically after Diagnostics is switched OFF, and retried after a failure. The UI reports the Run ID and GitHub link without asking the operator to upload files or screenshots.
- No live installation is performed as part of diagnostics implementation or testing.

## Explicit exclusions

- No log viewer/dashboard in this initial scope.
- No mobile remote control, multi-machine management, or Phase 6 work.
- No automatic GitHub uploads on each event; publishing occurs only on an explicit send or when Diagnostics is switched OFF.
- No independent native security review.
- No two-Windows-logon-session coordination tests.
- No changes to Real Install approval policy or execution semantics.
