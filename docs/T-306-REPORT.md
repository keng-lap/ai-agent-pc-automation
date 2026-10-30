# T-306 — Local Agent API Authorization

## Status

**Implementation and Product Owner Windows 11 verification complete.** T-306 was merged in PR #27 on 2026-10-30 (merge commit `4e9ebe937e3a40764e22b2062ff2dfd314e58a8b`). T-307's duplicate-token automated regression test was merged in PR #30 on 2026-10-30 (merge commit `7b12e92edaa4ffdd91946c27af6573c0fe68d69a`). The final Windows 11 test-script rerun after T-307 passed.

Product Owner approved D-SEC-1 option A on 2026-10-30.

## Approved decision

Require a random per-installation 256-bit token on every `/api/*` request. Keep the token in the ignored local `.env` file. The Angular development proxy injects the token into backend requests; it is not embedded in browser application code. The backend validates the token using constant-time comparison. Missing, invalid, or duplicate token headers are rejected. `/health` remains available without the token.

## Delivered

- Backend configuration requires a 64-character lowercase hexadecimal `LOCAL_AGENT_TOKEN`.
- Backend middleware requires `X-Local-Agent-Token` on `/api/*`.
- Setup generates 32 random bytes and stores the hex token in local `.env`.
- The development launcher validates the token before starting the services.
- The Angular development proxy injects the token server-side.
- Backend tests cover missing/invalid tokens, duplicate token headers, and Host, Origin, content-type, request-size, and health checks.
- No AI provider integration or real PC-changing execution is introduced.

## Verification evidence

**Environment:** Product Owner's Windows 11 PC; Windows PowerShell 5.1; Python 3.14.3; Node.js 26.3.0; npm 11.16.0. Clean clone: `D:\work\aiagent\aiagent2-clean`.

| Check | Result |
|---|---|
| `scripts/setup.ps1` | PASS |
| Final `scripts/test.ps1` after T-307 merge — backend pytest | PASS — 100 tests |
| Ruff | PASS — all checks passed |
| Frontend unit tests | PASS — 21 tests |
| Frontend production build | PASS |
| Development backend and frontend startup | PASS |
| `GET /health` without token | PASS — 200 |
| Direct backend `POST /api/chat` without token | PASS — rejected with 401 |
| Direct backend request with valid token | PASS — API response received |
| Frontend proxy `POST /api/chat` with allowed Origin | PASS — API response received |
| Production bundle token scan | PASS — token not found |
| Duplicate token header manual test | PASS — rejected with 401 |
| T-307 automated duplicate-token regression | PASS — merged in PR #30 |
| Agent Planner browser flow | PASS — deterministic local preview; no tool allowed and no PC changes |

The first direct PowerShell proxy probe returned 403 because it omitted the required `Origin` header. Repeating the same request with `Origin: http://127.0.0.1:4200` succeeded. This is expected enforcement, not a proxy defect.

After PR #30 merged, the Product Owner reran `scripts/test.ps1` on the clean clone. Final output: backend pytest 100 passed, Ruff all checks passed, frontend 21 tests passed, and the script reported “All checks passed.”

GitHub Actions checks on the T-307 PR head completed successfully for CodeQL, Python analysis, and JavaScript/TypeScript analysis. The PR #30 merge is recorded above.

## Remaining Phase 3 work

The T-307 duplicate-token regression gate is complete. The documented T-306/T-307 verification work is complete; overall Phase 3 closeout still requires review of the complete Phase 3 acceptance criteria and Product Owner approval. Do not start Phase 4 until Phase 3 closeout is explicitly approved and merged.

## Safety boundary

All machine-changing tools remain dry-run only. This task does not approve provider sign-in, provider API calls, external data transfer, or real PC-changing execution. ChatGPT remains a deterministic local-preview identifier; `Provider connected: False` is expected.
