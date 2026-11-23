# P6-609 B2 Windows 11 Home Acceptance

These scripts cover the remaining target-machine storage acceptance only. A separate test across two Windows logon sessions is explicitly out of scope and is not required.

The scripts do not enable the application worker, invoke WinGet, or install software.

## Preconditions

- Windows 11 Home.
- Repository checked out at the exact PR commit nominated for acceptance.
- Project virtual environment created with `scripts\setup.ps1`.
- 64-bit Python 3.11+ with pytest and pywin32 installed.
- Local fixed NTFS volume.
- Run in a normal, non-elevated PowerShell. If a native test is denied, record the failure; do not rerun elevated and treat it as equivalent.

## 1. Confirm repository and commit

From the repository root:

```powershell
git status --short
git rev-parse HEAD
```

Confirm the commit matches the PR head nominated for acceptance. Do not continue against a different or dirty checkout.

## 2. Run preflight

```powershell
.\scripts\acceptance\P6-609-B2\preflight.ps1
```

Expected: Windows 11 Home, 64-bit Python, pytest, and pywin32 checks pass. This step does not create the acceptance database.

## 3. Run storage and lifecycle tests

```powershell
.\scripts\acceptance\P6-609-B2\test-storage.ps1
```

Runs:
- `tests/backend/test_platform_storage.py`
- `tests/backend/test_job_store.py`

This includes the applicable Windows native directory/file protection, ACL, reparse-point, handle-lifetime, rename, and same-database mutex tests. It does not include a separate two-logon-session coordination test. Review the pytest summary: skipped mandatory cases are not passes.

## 4. Run Windows security regression tests

```powershell
.\scripts\acceptance\P6-609-B2\test-security.ps1
```

Runs the Windows-specific cases in `test_platform_storage.py`, including wrong-owner/broad-DACL and reparse-point rejection fixtures. A skipped required fixture is not acceptance.

## 5. Collect evidence

```powershell
.\scripts\acceptance\P6-609-B2\collect-results.ps1
```

Creates environment metadata and a ZIP under `artifacts\P6-609-B2`. Inspect the archive before sharing. It should contain test logs and environment metadata only; do not add secrets, tokens, database contents, or personal files.

## Pass criteria

- Preflight passes on Windows 11 Home.
- Storage/lifecycle suite exits 0.
- Windows security regression suite exits 0.
- No required native acceptance case is skipped.
- Evidence records the exact tested commit and environment.

A successful GitHub-hosted Windows workflow does not replace target-machine acceptance. These scripts do not authorize merge or live installation. PR #170 remains Draft until the remaining acceptance evidence and explicit Product Owner merge approval are satisfied.
