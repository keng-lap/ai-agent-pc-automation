# P6-609-B2 — Windows Secure SQLite Storage

## Status and authority

**Status: implementation contract; no Windows SQLite adapter is enabled by this document.**

This slice enables no worker, approval reservation, installer process, WinGet invocation, or machine-changing behavior. The existing Windows fail-closed behavior remains mandatory until implementation, Windows CI, target-machine acceptance, and independent security review pass.

Base reviewed: `main` at branch creation. Work is isolated on `feat/P6-609-b2-windows-sqlite-storage`.

## Problem statement

`SQLiteJobStore` delegates path protection to `SecureStorageAdapter`. Linux is enabled; Windows intentionally raises `PlatformStorageUnavailable`. The separate `WindowsSecretFile` implementation is useful reference code, but it is not a SQLite adapter: SQLite opens the database and its sidecars by pathname and creates/uses `-wal` and `-shm` files. A secure implementation must protect the complete SQLite file set and the path namespace for the full lifetime of each connection.

Do not simply call `WindowsSecretFile` on the main database file and then pass its path to sqlite3. That would leave SQLite sidecar creation and path substitution outside the verified-handle boundary.

## Proposed design

### 1. Dedicated private state directory

- Accept only an absolute local-drive path beneath a dedicated application-owned state directory; reject UNC/network paths, device paths, relative paths, and unsupported path forms.
- Open each ancestor component with `FILE_FLAG_OPEN_REPARSE_POINT`; inspect the opened handle, reject path-redirection reparse tags, verify directory type, and retain handles without `FILE_SHARE_DELETE` for the entire SQLite connection lifetime.
- Never take ownership of an existing directory. The final application state directory must be owned by the current process token's user SID.
- Apply and verify a protected DACL on the dedicated state directory. The DACL must grant access only to the current user SID and must provide the intended inheritance semantics for SQLite-created children. Do not alter ACLs on shared ancestors such as the user's profile directory.
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
