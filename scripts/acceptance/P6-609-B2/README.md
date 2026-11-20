# P6-609 B2 Windows 11 Home Acceptance Scripts

These scripts are for the manual target-machine acceptance gate only. They do not enable Windows production storage, open the application worker, invoke a package manager, or install software. Run them only against the exact commit identified for acceptance.

## Preconditions

- Windows 11 Home (the preflight checks the edition and build).
- The repository checked out at the exact commit named for acceptance.
- Project virtual environment created by `scripts\\setup.ps1`.
- 64-bit Python 3.11+ with project test dependencies and pywin32 installed.
- A local fixed NTFS volume. No Administrator elevation is expected for the ordinary test suite; if Windows denies a specific native test, record the failure rather than rerunning elevated and treating it as equivalent.
- For the cross-session test, two simultaneously running Windows sessions with the **same user SID** and different Windows session IDs. The holder must remain running while the probe executes. Do not sign out of the holder session.

## 1. Preflight

From the repository root in PowerShell:

```powershell
.\\scripts\\acceptance\\P6-609-B2\\preflight.ps1
```

This checks Windows 11 Home, Python version/architecture, pytest, and pywin32. It does not create the acceptance database.

## 2. Storage and lifecycle suite

```powershell
.\\scripts\\acceptance\\P6-609-B2\\test-storage.ps1
```

Runs `tests/backend/test_platform_storage.py` and `tests/backend/test_job_store.py`. The Windows-specific cases include native directory/file ACL, reparse-point, handle-lifetime, rename, and mutex tests. Tests that are platform-skipped are reported as skipped, not passed.

## 3. Windows security regressions

```powershell
.\\scripts\\acceptance\\P6-609-B2\\test-security.ps1
```

Runs the Windows-named cases in `test_platform_storage.py`, including wrong-owner/broad-DACL and reparse-point rejection fixtures. Review the pytest summary; a skipped mandatory fixture is not acceptance.

## 4. Two-session global mutex test

The probe creates persistent filesystem state: a dedicated acceptance directory, database file, and SQLite sidecar files. It does not use the application's live database path. The default path is:

`%LOCALAPPDATA%\\AI-Agent-PC-Automation\\acceptance\\P6-609-B2\\jobs.sqlite3`

Use the same exact database path in both sessions.

**Session A:** open PowerShell and run:

```powershell
.\\scripts\\acceptance\\P6-609-B2\\test-multisession.ps1 -Mode Hold -HoldSeconds 90
```

Wait for `LOCK_ACQUIRED`. Record the `windows_session_id` and `user_sid_sha256` printed in the JSON log. Leave this process running.

**Session B:** create or use a second simultaneously running Windows session for the same user account. Open PowerShell in the same repository checkout and run:

```powershell
.\\scripts\\acceptance\\P6-609-B2\\test-multisession.ps1 -Mode Probe
```

Record its `windows_session_id` and `user_sid_sha256`. The SID fingerprints must match and the Windows session IDs must differ. Expected result: `PASS_CONTENTION_BLOCKED`.

If Windows 11 Home cannot provide two simultaneous sessions with the same SID and distinct session IDs while keeping Session A alive, report this gate as **BLOCKED**. Do not sign out of Session A, substitute a different user, or claim a same-session test as cross-session evidence.

Return to Session A and wait for `LOCK_RELEASED`. Then run in Session B:

```powershell
.\\scripts\\acceptance\\P6-609-B2\\test-multisession.ps1 -Mode VerifyReleased
```

Expected result: `PASS_ACQUIRED_AFTER_RELEASE`. This confirms the mutex can be acquired after Session A releases its lease.

If Session B reports any error other than the expected mutex timeout, the cross-session gate has not passed. Capture both logs. Do not change ACLs or run as Administrator to make the test pass.

## 5. Collect evidence

```powershell
.\\scripts\\acceptance\\P6-609-B2\\collect-results.ps1
```

Creates an environment summary and ZIP under `artifacts\\P6-609-B2`. Existing ZIP archives are excluded from subsequent archives. Inspect the archive before sharing it. It should contain test logs and environment metadata only; do not add secrets, tokens, database contents, or personal files.

## Output and interpretation

- Logs are written to `artifacts\\P6-609-B2`.
- Each test runner exits nonzero on failure.
- A successful GitHub-hosted Windows workflow is not a substitute for this Windows 11 Home acceptance.
- A test skip, unsupported environment, wrong commit, wrong Windows edition, or unverified session identity is not a pass.
- These scripts do not grant merge or production-enablement approval. PR #169 remains Draft and unmerged until the remaining acceptance and Product Owner gates are satisfied.
