# P6-609 B2 Windows 11 Home Acceptance Scripts

These scripts are for the **manual target-machine acceptance gate only**. They do not enable Windows production storage, open the application worker, invoke a package manager, or install software. Do not run them until the PR's independent native security review is ready and the test head is explicitly identified.

## Preconditions

- Windows 11 Home (the preflight checks the edition and build).
- The repository checked out at the exact commit named by the project owner/reviewer.
- Project virtual environment created by `scripts\setup.ps1`.
- 64-bit Python 3.11+ with project test dependencies and pywin32 installed.
- A local fixed NTFS volume. No Administrator elevation is expected for the ordinary test suite; if Windows denies a specific native test, record the failure rather than rerunning elevated and treating it as equivalent.
- For the cross-session test, two independent Windows logon sessions for the **same user account/SID**. Use Fast User Switching / sign-out and sign-in as appropriate. Do not use a different account for session B.

## 1. Preflight

From the repository root in PowerShell:

```powershell
.\scripts\acceptance\P6-609-B2\preflight.ps1
```

This checks Windows 11 Home, Python version/architecture, pytest, and pywin32. It does not modify the storage adapter or create the database.

## 2. Storage and lifecycle suite

```powershell
.\scripts\acceptance\P6-609-B2\test-storage.ps1
```

Runs `tests/backend/test_platform_storage.py` and `tests/backend/test_job_store.py`. The Windows-specific cases include native directory/file ACL, reparse-point, handle-lifetime, rename, and mutex tests. Tests that are platform-skipped are reported as skipped, not passed.

## 3. Windows security regressions

```powershell
.\scripts\acceptance\P6-609-B2\test-security.ps1
```

Runs the Windows-named cases in `test_platform_storage.py`, including wrong-owner/broad-DACL and reparse-point rejection fixtures. Review the pytest summary; a skipped mandatory fixture is not acceptance.

## 4. Two-logon-session global mutex test

Use the same repository checkout and exact same absolute database path in both sessions. The default is:

`%LOCALAPPDATA%\AI-Agent-PC-Automation\B2-Acceptance\jobs.sqlite3`

**Session A:** open PowerShell and run:

```powershell
.\scripts\acceptance\P6-609-B2\test-multisession.ps1 -Mode Hold -HoldSeconds 90
```

Wait until it prints `LOCK_ACQUIRED`. Leave this process running.

**Session B:** switch to a second logon session for the same Windows user SID, open PowerShell in the same repository checkout, and run:

```powershell
.\scripts\acceptance\P6-609-B2\test-multisession.ps1 -Mode Probe
```

Expected result: `PASS_CONTENTION_BLOCKED`. This confirms session B reached the production lease and timed out while session A held the same global mutex.

Return to session A and wait for `LOCK_RELEASED`. Then run the Probe command once more in session B. It should now acquire and release the lease normally; the current helper's Probe mode intentionally treats successful acquisition as a failure while testing contention. For the post-release check, run the storage test suite again or use the dedicated acceptance evidence from a subsequent review-approved test procedure.

If session B reports any error other than the expected mutex timeout, the cross-session gate has **not** passed. Capture both logs and session identity/timestamps. Do not change ACLs, run as Administrator, or use a different user to make the test pass.

## 5. Collect evidence

```powershell
.\scripts\acceptance\P6-609-B2\collect-results.ps1
```

Creates an environment summary and ZIP under `artifacts\P6-609-B2`. Inspect the archive before sharing it. It should contain test logs and environment metadata only; do not add secrets, tokens, database contents, or personal files.

## Output and interpretation

- Logs are written to `artifacts\P6-609-B2`.
- Each test runner exits nonzero on failure.
- A successful GitHub-hosted Windows workflow is not a substitute for this Windows 11 Home acceptance.
- A test skip, unsupported environment, wrong commit, wrong Windows edition, or run under a different user SID is not a pass.
- These scripts do not grant merge or production-enablement approval. PR #169 must remain Draft and unmerged until all independent review and Product Owner gates are satisfied.
