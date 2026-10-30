# T-306 — Local Agent API Authorization

## Status

**Merged in PR #27 on 2026-10-30** (merge commit `4e9ebe937e3a40764e22b2062ff2dfd314e58a8b`). Product Owner approved D-SEC-1 option A on 2026-10-30.

Implementation and Product Owner Windows 11 verification are complete. A dedicated automated regression test for duplicate token headers is being added in T-307; Phase 3 remains open until that test is merged and the final suite is rerun.

## Approved decision

Require a random per-installation 256-bit token on every `/api/*` request. Keep the token in the ignored local `.env` file. The Angular development proxy injects the token into backend requests; it is not embedded in browser application code. The backend validates the token using constant-time comparison. Missing, invalid, or duplicate token headers are rejected. `/health` remains available without the token.

## Delivered

- Backend configuration requires a 64-character lowercase hexadecimal `LOCAL_AGENT_TOKEN`.
- Backend middleware requires `X-Local-Agent-Token` on `/api/*`.
- Setup generates 32 random bytes and stores the hex token in local `.env`.
- The development launcher validates the token before starting the services.
- The Angular development proxy injects the token server-side.
- Existing backend tests cover missing/invalid tokens and Host, Origin, content-type, request-size, and health checks.
- No AI provider integration or real PC-changing execution is introduced.

## Verification evidence

**Environment:** Product Owner's Windows 11 PC; Windows PowerShell 5.1; Python 3.14.3; Node.js 26.3.0; npm 11.16.0. Clean clone: `D:\work\aiagent\aiagent2-clean`.

| Check | Result |
|---|---|
| `scripts/setup.ps1` | PASS |
| `scripts/test.ps1` backend pytest | PASS — 100 tests |
| Ruff | PASS |
| Frontend unit tests | PASS — 21 tests |
| Frontend production build | PASS |
| Development backend and frontend startup | PASS |
| `GET /health` without token | PASS — 200 |
| Direct backend `POST /api/chat` without token | PASS — rejected with 401 |
| Direct backend request with valid token | PASS — API response received |
| Frontend proxy `POST /api/chat` with allowed Origin | PASS — API response received |
| Production bundle token scan | PASS — token not found |
| Duplicate token header manual test | PASS — rejected with 401 |
| Agent Planner browser flow | PASS — deterministic local preview; no tool allowed and no PC changes |

The first direct PowerShell proxy probe returned 403 because it omitted the required `Origin` header. Repeating the same request with `Origin: http://127.0.0.1:4200` succeeded. This is expected enforcement, not a proxy defect.

The GitHub Actions run associated with current `main` commit `b2b029bc11e5d3ac7d9a91f8c28321d4ad5851b8` reports success for the dynamic CodeQL workflow. This is not a substitute for the local pytest/Ruff/frontend test results.

## Remaining regression gate

- T-307 adds a backend automated regression test proving duplicate `X-Local-Agent-Token` headers receive 401. The implementation already rejects duplicate headers; the manual Windows 11 test confirmed this behavior.
- After T-307 is merged, rerun `scripts/test.ps1` on the clean clone and record the final result before closing Phase 3.

## Safety boundary

All machine-changing tools remain dry-run only. This task does not approve provider sign-in, provider API calls, external data transfer, or real PC-changing execution. ChatGPT remains a deterministic local-preview identifier; `Provider connected: False` is expected.
