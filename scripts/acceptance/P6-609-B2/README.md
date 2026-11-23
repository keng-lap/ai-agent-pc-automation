# P6-609 B2 Windows 11 Home Acceptance

These scripts cover the remaining target-machine storage acceptance only. A separate test across two Windows logon sessions is explicitly out of scope and is not required.

The scripts do not enable the application worker, invoke WinGet, or install software. They print test results and failures directly in the PowerShell window. No log, ZIP, screenshot, or other artifact needs to be sent back.

## Preconditions

- Windows 11 Home.
- Repository checked out at the exact PR commit nominated for acceptance.
- Project virtual environment created with `scripts\setup.ps1`.
- 64-bit Python 3.11+ with pytest and pywin32 installed.
- Local fixed NTFS volume.
- Run in a normal, non-elevated PowerShell. If a native test is denied, report the displayed error; do not rerun elevated and treat it as equivalent.

## Run acceptance

From the repository root:

1. Confirm the checkout:

   ```powershell
   git status --short
   git rev-parse HEAD
   ```

   Confirm the commit matches the PR head nominated for acceptance. Do not continue against a different or dirty checkout.

2. Run preflight:

   ```powershell
   .\scripts\acceptance\P6-609-B2\preflight.ps1
   ```

3. Run storage and lifecycle tests:

   ```powershell
   .\scripts\acceptance\P6-609-B2\test-storage.ps1
   ```

   Runs `tests/backend/test_platform_storage.py` and `tests/backend/test_job_store.py`. This includes applicable Windows native directory/file protection, ACL, reparse-point, handle-lifetime, rename, and same-database mutex tests. It does not include a separate two-logon-session coordination test.

4. Run Windows security regression tests:

   ```powershell
   .\scripts\acceptance\P6-609-B2\test-security.ps1
   ```

   Runs the Windows-specific cases in `test_platform_storage.py`, including wrong-owner/broad-DACL and reparse-point rejection fixtures.

## Report in Chat

Do not send files. Report only the status and, for any failure, the actual failing test and concise error printed by pytest/PowerShell:

```text
Preflight: PASS
Storage: FAIL — test_name: actual exception/error summary
Security: PASS
```

For a passing suite, use `PASS`. For a suite that could not be run, use `BLOCKED — short reason`. For a failure, do not report only an exit code: include the failed test name and actual error text shown in the console. If all suites pass, no error details are needed.

## Pass criteria

- Preflight passes on Windows 11 Home.
- Storage/lifecycle suite exits 0.
- Windows security regression suite exits 0.
- No required native acceptance case is skipped.

A successful GitHub-hosted Windows workflow does not replace target-machine acceptance. These scripts do not authorize merge or live installation. PR #170 remains Draft until the remaining acceptance and explicit Product Owner merge approval are satisfied.
