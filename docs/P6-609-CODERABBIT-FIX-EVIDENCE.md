# P6-609 CodeRabbit Fix Evidence

This record tracks the three current CodeRabbit findings from PR #171. A finding is closed only after its code change, targeted regression test, and CI result are recorded. Outdated comments are not treated as proof of a fix.

## Finding 1 — Readiness must use the worker's effective configuration

- Review thread: `PRRT_kwDOU_JsvM6690a-`
- Original location: `src/backend/agent_backend/software_install_api.py:65`
- Root cause: readiness reparsed process environment independently of the Settings snapshot used by `create_app()` to decide whether to start the worker. This could report real installation enabled while the worker was disabled.
- Fix: readiness now reads `request.app.state.real_install_enabled` and `request.app.state.real_install_release_authorization`, the same values installed by `create_app()`; it suppresses expired authorization at request time.
- Regression test: `test_readiness_uses_worker_configuration_not_process_environment` in `tests/backend/test_software_install_api.py`.
- Code commit: `7c991cb31a3546c0ff0b5009fe200c10a2f4c6eb`
- Test commit: `675f05b013bf5fb81f3d6401c7e0a862ab44ed79`
- CI evidence: PASS on head `9b8ebae585ecad3da6e4e7f095d12668897d394a` (8/8 GitHub Actions checks).
- Status: VERIFIED — targeted regression test and CI passed.

## Finding 2 — Reservation recovery must take precedence over release authorization UI

- Review thread: `PRRT_kwDOU_JsvM6690bM`
- Original location: `src/frontend/src/app/app.html:571`
- Root cause: the release-authorization branch rendered before the reservation-recovery branch. If readiness became disabled while confirmation outcome was unresolved, the UI hid the recovery retry and offered a refresh that could discard the proposal context.
- Fix: the `reservationRecoveryPending` branch now renders before both the approval challenge and release-authorization branches. It remains visible while readiness changes.
- Regression test: `keeps reservation recovery visible when readiness is revoked mid-recovery` in `src/frontend/src/app/app.spec.ts`.
- Code commit: `5f087a72e9809c725721ee6f922249221c542338`
- Test commit: `e8b03c9c9dca23a57c7cdfe872c2e509690c7291`
- CI evidence: PASS on head `9b8ebae585ecad3da6e4e7f095d12668897d394a` (8/8 GitHub Actions checks).
- Status: VERIFIED — targeted regression test and CI passed.

## Finding 3 — A definitive confirmation 404 must discard the expired proposal

- Review thread: `PRRT_kwDOU_JsvM6690cG`
- Original location: `src/frontend/src/app/app.ts:1002`
- Root cause: confirmation 404 was treated like an ambiguous commit and sent through reservation recovery. If the plan had expired before confirmation, recovery also returned 404, but the stale proposal remained and the UI could not prepare a new proposal.
- Fix: a definitive confirmation 404 now clears the proposal and challenge, exits recovery, and returns the UI to installer preparation. Ambiguous failures continue through reservation recovery.
- Regression test: `clears a definitively missing proposal and offers installer preparation again` in `src/frontend/src/app/app.spec.ts`.
- Code commit: `43d41e6dae8508e38283d812f9edd2df2a920be5`
- Test commit: `9b8ebae585ecad3da6e4e7f095d12668897d394a`
- CI evidence: PASS on head `9b8ebae585ecad3da6e4e7f095d12668897d394a` (8/8 GitHub Actions checks).
- Status: VERIFIED — targeted regression test and CI passed.

## Verification results

- Commit verified by CI: `9b8ebae585ecad3da6e4e7f095d12668897d394a`.
- GitHub Actions: 8/8 checks succeeded — backend, frontend (unit tests and build), Windows Real Install Frontend (unit tests and build), Windows DPAPI, WinGet Adapter, Generic Publisher Trust, Process Containment, and trigger.
- Backend regression suite: PASS.
- Frontend regression suite: PASS, including both newly added reservation/proposal regression cases.
- No live installer was executed.

## Verification policy

- Do not rerun Full Review solely to re-check these three findings.
- Do not resolve a thread until the targeted regression test and required CI checks pass.
- If the same finding is reported again, compare the new comment to this record and the cited commit/test before changing code.
- No live Windows install is performed by CI.
- PR #171 remains stacked on `feat/P6-609-C-winget-execution`; this record does not authorize merging #170 or merging to main.
