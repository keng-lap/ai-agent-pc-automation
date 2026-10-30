# T-306 — Local Agent API Authorization

## Status

Implementation is in progress on `feat/t-306-local-agent-auth`. Product Owner approved D-SEC-1 option A on 2026-10-30. This report is a work-in-progress record, not a completion claim.

## Approved decision

Require a random per-installation 256-bit token on every `/api/*` request. Keep the token in the ignored local `.env` file. The Angular development proxy injects the token into backend requests; it is not embedded in browser application code. The backend validates the token using constant-time comparison. Missing, invalid, or duplicate token headers are rejected. `/health` remains available without the token.

## Changes currently on this branch

- Backend configuration requires a 64-character lowercase hexadecimal `LOCAL_AGENT_TOKEN`.
- Backend middleware requires `X-Local-Agent-Token` on `/api/*`.
- Setup generates 32 random bytes and stores the hex token in local `.env`.
- The development launcher validates the token before starting the services.
- The Angular development proxy injects the token server-side.
- Backend tests cover missing/invalid tokens and retain existing Host, Origin, content-type, request-size, and health checks.
- No AI provider integration or real PC-changing execution is introduced.

## Verification still required

- Run the complete backend test suite and Ruff on changed Python files.
- Run frontend build/tests and verify the Angular proxy injects the token without exposing it to browser bundles.
- Verify setup and startup on the Product Owner's Windows 11 machine.
- Verify direct requests to the backend without a token fail with 401, while the local web app can still use chat.
- Review the complete diff and GitHub Actions results.

## Safety boundary

All machine-changing tools remain dry-run only. This task does not approve provider sign-in, provider API calls, external data transfer, or real PC automation. Phase 3 must remain open until T-306 is merged and its acceptance checks are verified.
