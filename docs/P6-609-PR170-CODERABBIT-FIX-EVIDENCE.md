# P6-609 PR #170 — CodeRabbit Fix Evidence

This record distinguishes findings already addressed in the current branch from the one unresolved Windows storage release gate. Do not repeat fixes or trigger Full Review for findings with the evidence below.

## Verified / addressed findings

### 1. Reservation ID format
- Review thread: `PRRT_kwDOU_JsvM662R0-`
- Store creates canonical hyphenated UUIDs with `str(uuid.uuid4())`.
- Status endpoint accepts canonical UUIDs as well as legacy 32-character hex IDs.
- Regression: `test_install_job_status_accepts_canonical_uuid_reservation_id` in `tests/backend/test_software_approval_api.py`.
- Frontend validates canonical RFC UUIDs; the new reservation recovery regression uses a valid UUIDv4 variant.
- Status: VERIFIED IN CURRENT CODE.

### 2. Gemini SDK minimum
- Review thread: `PRRT_kwDOU_JsvM662R1n`
- `src/backend/pyproject.toml` requires `google-genai>=1.22.0`, which supports `GenerateContentConfig.response_json_schema`.
- Status: VERIFIED IN CURRENT CODE.

### 3. Owner-scoped confirmation lookup
- Review thread: `PRRT_kwDOU_JsvM662R1v`
- Confirmation calls `_get_install_plan(plan_id, owner_id=principal.owner_sub)`.
- Regression: `test_confirm_consumes_exact_digest_and_persists_queued_install` asserts the authenticated owner is passed; cross-session confirmation is rejected.
- Status: VERIFIED IN CURRENT CODE.

### 4. Real-install Product Owner release gate
- Review thread: `PRRT_kwDOU_JsvM662R1y`
- App startup starts the worker only when `settings.real_install_enabled` is true.
- Confirmation requires the current release authorization for task `P6-609-C` and the exact package/version before consuming TOTP.
- Immediately before invoking the executor, the worker checks the same task/package/version and atomically consumes the exact action digest, expiry, and one-use nonce in the durable store. The nonce is a primary key and release-consumption rows are append-only.
- Regression coverage: `test_confirm_rejects_missing_exact_release_before_consuming_totp` and worker denial cases for missing authorization, wrong task, wrong version, replay, expiry, and unavailable authorization storage.
- Status: VERIFIED IN CURRENT CODE; do not remove or weaken this gate.

### 5. Recover a committed reservation after an ambiguous confirmation result
- Review thread: `PRRT_kwDOU_JsvM662R15`
- Store exposes owner-scoped `get_install_job_for_plan(plan_id, owner_id)`; API exposes the authenticated plan-owner recovery route; frontend invokes it after ambiguous confirmation failures without issuing another approval or dispatch.
- Existing backend regression: `test_owner_can_recover_committed_install_job_by_plan_without_new_approval`.
- Added backend regression: `test_committed_install_can_be_recovered_after_post_commit_lease_failure`, which simulates the post-commit lease verification failure and recovers the already-queued job.
- Added frontend regression: `recovers a committed reservation after an ambiguous confirmation failure`, which checks the recovered reservation ID is used for status lookup.
- Status: VERIFIED — backend and frontend regression tests passed.

### 6. EXE silent installer switch
- Review thread: `PRRT_kwDOU_JsvM662R1-`
- EXE evidence requires a nonblank backend-verified silent switch. The local WinGet manifest builder writes it to `InstallerSwitches.Silent` and rejects missing switches. No model/client-supplied switch is used.
- Regressions: `test_exe_manifest_includes_backend_verified_silent_switch` and `test_exe_evidence_without_manifest_silent_switch_is_rejected` in `tests/backend/test_winget_adapter.py`.
- Status: VERIFIED IN CURRENT CODE.

### 7. WinGet inventory: package absent vs query failure
- Review thread: `PRRT_kwDOU_JsvM662R2F`
- `verify_exact_user_install` maps WinGet `APPINSTALLER_CLI_ERROR_NO_APPLICATIONS_FOUND` (`0x8A150014`, signed equivalent) to `False`; other nonzero query errors remain ambiguous (`None`).
- Regression: `test_verifier_treats_winget_no_applications_result_as_absent` exercises both actual return-code representations.
- Status: VERIFIED IN CURRENT CODE.

### 8. Frontend recovery after confirmation timeout
- Review thread: `PRRT_kwDOU_JsvM662R2d`
- Ambiguous confirmation failures preserve the proposal/plan ID and call the owner-scoped reservation recovery route. A recovered receipt is attached to the card and its job status is loaded; no second approval is created.
- Backend coverage: owner-scoped recovery route test above.
- Frontend regression added in `src/frontend/src/app/app.spec.ts`: `recovers a committed reservation after an ambiguous confirmation failure`.
- Test commit: `f351891b69ae7a150e174d50311756c62bf82de7`.
- Status: IMPLEMENTED; CI VERIFICATION PENDING.

## Windows storage acceptance status after Product Owner decision (2026-11-24)

- Review thread: `PRRT_kwDOU_JsvM662R1j`
- The Product Owner confirmed that Independent Native Security Review is not an available project activity and instructed that this prerequisite be removed. Do not create a separate review task or substitute review process.
- The independent-review prerequisite is removed. Remaining technical acceptance items are Windows 11 Home target-machine acceptance and the outstanding native acceptance matrix (wrong-owner/broad-DACL database and sidecar fixtures, database/sidecar reparse-point fixtures, and explicit no-fallback behavior).
- This is a documentation/release-gate correction only. It does not claim that unperformed Windows acceptance tests have passed.
- Status: independent-review prerequisite REMOVED; remaining technical acceptance items remain OPEN. PR #170 stays Draft and unmerged pending those results and explicit Product Owner merge approval.

## Additional Product Owner scope decision (2026-11-24)

- A separate two-logon-session coordination test is not required and is removed from the release gates.
- Do not create a task or block PR #170 on that test.
- Existing mutex implementation and same-database/alias contention coverage remain unchanged.
- Windows 11 Home target-machine acceptance and the remaining native wrong-owner/broad-DACL, reparse-point, and no-fallback acceptance cases remain open.

## Verification record
