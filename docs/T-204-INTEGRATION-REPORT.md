# T-204 Integration Verification Report

## Status

Implementation and automated verification are complete on branch `feat/t-204-integration`. The Product Owner reported MV-01 to MV-14 passed on 2026-10-23. PR #18 was merged into `main` on 2026-10-23 (merge commit `94c09a37601e2cb2364a7c478940daf10e982569`).

Base commit: `8ad6d46513ddb7fced10112213bad7d9e429eaeb` (main after PR #17).

## Changes

- Replaced the disconnected `ChatApi` with an Angular `HttpClient` POST to `/api/chat`.
- Added the `HttpClient` provider.
- Configured the Angular development proxy to forward `/api` to loopback using `BACKEND_PORT`; invalid port values fail closed. `changeOrigin` sets the backend Host while the browser Origin is forwarded for the T-205 checks.
- Completed error classification for HTTP parse errors at status 200 and for Angular `HttpErrorResponse` JSON bodies containing a string `detail`.
- Left backend behavior, runtime dependencies, and existing script behavior unchanged.

## Automated and integration evidence

| Check | Result |
|-------|--------|
| `scripts/test.ps1` | Passed: 73 backend tests, Ruff, 21 frontend tests |
| I-01 | Thai and English replies matched the direct backend response for 20 requests per language; every request completed in under 1 second |
| I-02 | With backend stopped, the proxy returned HTTP 502; the UI maps it to MSG-03 |
| I-03 | Foreign Origin through the proxy returned 403 |
| I-04 | Direct backend request with foreign Host returned 400 |
| I-05 | Ports 4200 and 8000 were unreachable on non-loopback address `192.168.1.43` |
| I-06 | With `BACKEND_PORT=18000` and `FRONTEND_PORT=14200`, matching Origin was accepted and returned the exact backend reply; old Origin returned 403 |
| I-07 | `scripts/test.ps1` passed; test counts remain above baseline |

## Product Owner manual verification

| ID | Result | Evidence |
|----|--------|----------|
| MV-01 to MV-14 | Passed | Product Owner report received 2026-10-23; individual observations were not provided |

ST-24 is owned by T-202; T-204 covers ST-22 through I-03.