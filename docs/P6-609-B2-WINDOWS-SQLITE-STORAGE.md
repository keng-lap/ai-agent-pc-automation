# P6-609-B2 — Windows Secure SQLite Storage

## Status and authority

**Status: implementation in progress; Windows SQLite storage remains disabled.**

The shared storage contract and `SQLiteJobStore` use a connection-scoped protection lease. The Windows adapter now pins ancestor directory handles, creates or opens the final state directory relative to a pinned immediate-parent handle with NtCreateFile, receives and retains the exact created/opened directory handle, applies an explicit protected owner-only DACL during creation, refuses to rewrite ACLs on existing directories, rejects all reparse points, requires a fixed local volume, and verifies database/sidecar owner and inherited DACL. These changes are not yet accepted for production: Windows integration coverage, independent review, exact-head CI, and Windows 11 Home acceptance remain required.

This slice enables no worker, approval reservation, installer process, WinGet invocation, or machine-changing behavior. The existing Windows fail-closed behavior remains mandatory until implementation, Windows CI, target-machine acceptance, and independent security review pass.

Base reviewed: `main` at branch creation. Work is isolated on `feat/P6-609-b2-windows-sqlite-storage`.

## Problem statement

`SQLiteJobStore` delegates path protection to `SecureStorageAdapter`. Linux is enabled; Windows has a native adapter implementation but intentionally remains disabled by `create_platform_secure_storage()` pending review and acceptance. The separate `WindowsSecretFile` implementation is useful reference code, but it is not a SQLite adapter: SQLite opens the database and its sidecars by pathname and creates/uses `-wal` and `-shm` files. A secure implementation must protect the complete SQLite file set and the path namespace for the full lifetime of each connection.

Do not simply call `WindowsSecretFile` on the main database file and then pass its path to sqlite3. That would leave SQLite sidecar creation and path substitution outside the verified-handle boundary.

## Proposed design

### 1. Dedicated private state directory

- Accept only an absolute local-drive path beneath a dedicated application-owned state directory; reject UNC/network paths, device paths, relative paths, and unsupported path forms.
- Open each ancestor component with `FILE_FLAG_OPEN_REPARSE_POINT`; inspect the opened handle, reject path-redirection reparse tags, verify directory type, and retain handles without `FILE_SHARE_DELETE` for the entire SQLite connection lifetime.
- Never take ownership of an existing directory. The final application state directory must be owned by the current process token's user SID.
- Create a new dedicated state directory atomically with an explicit protected DACL granting access only to the current user SID, including intended inheritance for SQLite-created children. For an existing directory, verify the exact owner/DACL and fail closed if it differs; never rewrite an existing directory ACL. Do not alter ACLs on shared ancestors such as the user's profile directory.
- If any ancestor cannot be pinned or verified, fail closed before SQLite opens the database.

### 2. Database and sidecar protection

- Treat the following as one protected file set: database, `-wal`, `-shm`, and any SQLite journal file used by the configured journal mode.
- Before connecting, inspect any existing member through a handle opened with `FILE_FLAG_OPEN_REPARSE_POINT`; reject directories, path-redirection reparse points, wrong-owner files, and DACLs that grant access to any other SID.
- Configure WAL, foreign keys, `synchronous=FULL`, and busy timeout only after the protected directory lease is active.
- The directory DACL must ensure newly created WAL/SHM/journal files inherit owner-only access. Verify the actual owner and effective DACL of the database and any sidecar after SQLite has opened/created them. If verification fails, close the SQLite connection and all handles, then fail closed.
- Keep the directory lease and its pinned handles alive until the SQLite connection is closed. No adapter method may return after checking a path while releasing the handles before SQLite uses that path.
- Do not unlink, rename, or repair an unsafe database/sidecar automatically. Preserve evidence and report storage unavailable.

### 3. Adapter lifecycle contract

Replace the current prepare/finalize-only contract with a connection-scoped protection lease (or an equivalent API that cannot release the pinned directory handles before the SQLite connection closes).

The lease must:
1. Secure and pin the directory ancestry.
2. Validate existing database and sidecar entries.
3. Permit SQLite to open the database only while the lease is held.
4. Verify database and sidecar owner/DACL state after SQLite opens and after sidecar creation.
5. Keep handles pinned until SQLite connection close.
6. Close all native handles deterministically on success and every exception path.

`SQLiteJobStore` must own the lease and SQLite connection in one context manager. A path-only `prepare_database_path()` / `finalize_database_file()` sequence is insufficient for Windows and must not be used to enable Windows.

### 4. Failure and compatibility behavior

- Windows remains disabled until the new lease API is implemented and reviewed.
- Linux behavior and tests remain unchanged unless the shared protocol requires a strictly backward-compatible refactor.
- macOS remains disabled.
- Missing pywin32, access denied, unexpected DACL entries, owner mismatch, reparse points, handle acquisition failures, sidecar verification failures, and SQLite errors all fail closed as `JobStoreUnavailable`.
- No fallback to a temporary directory, weaker ACL, non-WAL mode, process-local store, or unprotected database is allowed.
- Do not change Phase 5 Dry Run behavior.

## Required tests

### Windows hosted-runner integration tests

Add a dedicated Windows workflow job (or extend `.github/workflows/windows-process-containment.yml`) to run the following against real NTFS paths:

1. New database directory and database have the expected current-user owner and protected owner-only DACL.
2. WAL mode creates `-wal` and `-shm` as applicable; every present sidecar has the expected owner and owner-only effective DACL.
3. Reopen a second store instance and prove persisted jobs/events survive close/reopen.
4. Keep a store connection open and prove ancestor directory rename/replacement is denied while its protection lease is held.
5. Reject a symlink/junction/mount-point ancestor and a database or sidecar reparse point.
6. Reject wrong-owner and broad-DACL database/sidecar fixtures without silently repairing or taking ownership.
7. Fail closed when pywin32/security APIs are unavailable or mocked to fail.
8. Exercise exception cleanup and prove every native handle is released.
9. Exercise concurrent store instances and SQLite busy/locking behavior without weakening durability.
10. Confirm no unsafe fallback occurs when storage initialization fails.

### Cross-platform regression and quality gates

- Existing Linux `test_platform_storage.py` and `test_job_store.py` remain green.
- Add protocol/lifecycle tests proving the protection lease encloses the SQLite connection lifetime.
- Run backend pytest and Ruff; Ruff must pass before review.
- Windows workflow must be green on the exact PR head, not a previous commit.
- Target acceptance on the user's Windows 11 Home machine is still required; hosted Windows CI is not a substitute.

## Security review gates

Before enabling Windows storage:
- Review native handle lifetime, DACL inheritance, owner verification, reparse tags, and SQLite sidecar behavior.
- Review the exact final PR head independently (A4).
- Confirm the Windows hosted-runner evidence and target Windows 11 Home acceptance.
- Keep approval reservation, worker dispatch, and real installation disabled until their separate gates pass.

## Explicit non-goals

This slice does not implement durable approval, TOTP integration, execution audit, worker scheduling, suspended process creation, Job Object dispatch, package-manager adapters, publisher trust anchors, or real installation.


## Security review remediation status (2026-11-20)

The first independent review identified four blocking concerns. The current implementation addresses them as follows, but this is not a final approval:

- **First-run ACL window:** new directories are created relative to a pinned parent with `NtCreateFile`; the protected owner-only security descriptor is supplied in that same native call, and the returned handle is verified directly.
- **Existing directory mutation:** existing directories are never re-permissioned. They must already have the exact protected owner-only ACL or initialization fails closed.
- **Mapped/network drives:** `GetDriveTypeW` must report `DRIVE_FIXED`; mapped network and removable volumes are rejected.
- **Reparse points:** every reparse point is rejected until a specific provider/tag is separately reviewed and allow-listed.

Windows storage remains disabled in the production factory. The new Windows regression tests cover rejection of arbitrary reparse tags, mapped drive types, and non-private pre-existing state directories without ACL mutation. Additional native Windows acceptance cases in the checklist above remain open.


## Parent namespace race remediation attempt (2026-11-20)

The final state-directory operation no longer uses a path-based CreateDirectoryW followed by a separate path-based open. The adapter now:

1. Pins the final directory's immediate parent with `FILE_ADD_SUBDIRECTORY` and without `FILE_SHARE_DELETE`; it does not request `FILE_DELETE_CHILD`.
2. Creates the child relative to that pinned parent using NtCreateFile, supplying the protected owner-only security descriptor in the same call.
3. Retains the handle returned by NtCreateFile (or opens the pre-existing child relative to the same parent after a create collision) and verifies that exact handle before SQLite is allowed to open the database.

This is intended to bind creation/open and verification to the same directory object, removing the former create-then-reopen-by-path substitution window. It is **not yet accepted as closed**: the exact-head Windows native workflow must validate the NtCreateFile structure/handle interop and all existing Windows acceptance tests, followed by independent review. Windows storage remains disabled and this PR remains Draft.


Additional native Windows tests now attempt to prove that the leased state directory cannot be renamed while its handle is held, and that all directory handles are released after a forced verification failure. These tests must pass on the exact PR head before the parent namespace mitigation can be considered validated.


**Historical attempt (superseded):** an earlier revision added `FILE_DELETE_CHILD` to the parent handle after the first rename test. That access right was subsequently removed; it is not requested by the current implementation.


## Rename-lease CI finding and correction (2026-11-20)

The exact-head Windows test showed that omitting `FILE_SHARE_DELETE` was not sufficient when the final directory handle requested metadata-only access. The final directory handle now requests `FILE_LIST_DIRECTORY` together with `SYNCHRONIZE`, while continuing to omit `FILE_SHARE_DELETE`. The earlier `FILE_DELETE_CHILD` request on the immediate-parent handle was removed to preserve least privilege.


## Exact-head CI result (2026-11-20)

Exact PR head: `ed89fe06e7e47f9beb4493406194332fd0748e84`.

- CI workflow: **passed** — backend tests, AI reviewer unit tests, Ruff, frontend unit tests, Playwright desktop/mobile viewport E2E, and frontend build.
- Windows Process Containment workflow: **passed** — Windows native storage/job lifecycle and containment test job completed successfully.
- The rename-lease regression and exception-path handle-cleanup regression are included in that exact-head Windows job.

This closes the CI validation requirement for this revision only. It does not grant independent security approval or Windows 11 Home target-machine acceptance. The broader acceptance matrix (including wrong-owner/broad-DACL database and sidecar fixtures, reparse-point database/sidecar fixtures, concurrent store instances, and explicit no-fallback tests) remains to be completed. Windows storage remains fail-closed; this PR remains Draft.


## Concurrent store-instance regression (2026-11-20)

Added a Windows-native integration test that opens two independent `SQLiteJobStore` instances against the same protected NTFS database, submits twelve writes concurrently through both instances, and verifies that all committed jobs are recoverable. This extends the Windows acceptance coverage for concurrent store instances and SQLite locking. The test must pass on the exact PR head; it does not replace the remaining wrong-owner/broad-DACL and reparse-point database/sidecar fixtures.

## Concurrent first-open owner race remediation (2026-11-20)

**Historical failure:** an earlier implementation attempted to correct the owner SID of newly observed SQLite entries. A concurrent lease could classify an entry before that correction completed. That owner-correction approach has been removed: the current implementation never changes a database or sidecar owner and rejects any entry whose owner SID is not already the current user.

The adapter continues to acquire a per-user, per-canonical-database-path Windows named mutex before pinning the directory and taking the database/sidecar snapshot. The mutex remains held for the complete protection-lease and SQLite-connection lifetime, including post-open owner/DACL verification and connection close. This deliberately serializes access to the same protected database across independent store instances/processes; it favors deterministic security initialization over parallel connections. Different database paths remain independent. The mutex uses the Windows local-session namespace and the OS-created default security descriptor; its namespace ACL and cross-session assumptions still require independent security review. A Windows-native integration test now holds one lease while a second store instance attempts to acquire the same database lease, proving that the second cannot enter until the first releases it.

The Windows concurrent-store integration test must pass on the exact new head. This is a race-remediation attempt, not security approval; Windows storage remains disabled and the PR remains Draft.


## Review remediation after CodeRabbit review (2026-11-20)

- The Windows workflow path filters now include `src/backend/agent_backend/jobs_api.py` for both pull-request and main-branch push events.
- The current directory-creation description names `NtCreateFile` as the API receiving the protected security descriptor. The former `CreateDirectoryW` and `FILE_DELETE_CHILD` statements are explicitly identified as superseded attempts.
- SQLite initialization now checks the returned `PRAGMA journal_mode = WAL` value and fails closed unless SQLite reports `wal`.
- Linux lease acquisition verifies existing database and sidecar entries before yielding to SQLite. Verification opens each entry once with no-follow semantics and applies ownership/mode checks through the opened descriptor; a sidecar that disappears before open is treated as absent.
- Windows file verification no longer changes an entry's owner based on absence from a pathname snapshot. It requires the current-user SID as found and rejects mismatches without modifying the entry. Same-database leases remain serialized by the named mutex.
- Native pywin32 errors are translated at the Windows adapter boundary to `PlatformStorageUnavailable`, which the job store translates to `JobStoreUnavailable`; exception paths retain ExitStack cleanup.
- The job store reports `JobStoreCommittedButUnverified` when a progress update or transition has committed but the subsequent storage verification fails. Callers must not blindly retry; after storage is trusted again, they should read the job ID and reconcile its persisted state with the intended update.
- Regression coverage records the SQLite-open event after lease entry, tracks all directory handles in the forced-failure cleanup test, tests pre-existing Linux sidecar rejection before SQLite connects, and exercises same-database Windows mutex serialization.

These changes do not enable Windows storage. The production factory remains fail-closed. The Windows named-mutex namespace/security descriptor, broader Windows wrong-owner and broad-DACL fixtures, database/sidecar reparse-point fixtures, and independent native interop review remain acceptance gates.
