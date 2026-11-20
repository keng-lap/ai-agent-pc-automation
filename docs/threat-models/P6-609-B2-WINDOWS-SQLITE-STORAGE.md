# P6-609 B2 — Windows SQLite Storage Threat Model

**Status:** Engineering threat-model draft for review. This document is not an independent security assessment or approval.  
**Scope:** The Windows SQLite storage protection adapter and its interaction with the SQLite job store.  
**Implementation under review:** PR #169, branch `feat/P6-609-b2-windows-sqlite-storage`.  
**Security posture:** Windows production storage remains disabled and fail-closed.

## 1. Security objectives and assets

The B2 storage boundary must preserve:

1. **Confidentiality:** job data and SQLite journal/sidecar contents are readable only by the intended Windows user identity and explicitly required system components.
2. **Integrity:** an untrusted local process must not substitute the database directory or files, weaken their ACLs, or bypass same-directory serialization while the store is in use.
3. **Consistency:** concurrent processes and logon sessions for the same user must not initialize or mutate the same SQLite database outside the intended coordination boundary.
4. **Availability:** unsafe paths, unsupported ACL forms, native API failures, mutex timeouts, or unverified storage state fail closed rather than silently falling back to weaker storage.
5. **Auditability:** a failed post-commit verification must remain distinguishable from a transaction that definitely did not commit.

Assets include the database, `-wal`, `-shm`, and `-journal` files; owner and DACL metadata; pinned directory/file handles; named mutex namespace and ownership; persisted job state and version; and the integrity of the fail-closed platform selection.

## 2. Scope and trust boundaries

### In scope

- Windows path validation and fixed-local-drive restriction.
- Pinning of ancestor directories and the dedicated state directory.
- Reparse-point rejection for ancestors, state directory, database, and SQLite sidecars.
- Native `NtCreateFile` directory creation/open relative to a pinned parent handle.
- Explicit owner and protected DACL creation/verification for the state directory and SQLite file set.
- Directory-identity-based global named mutex and timeout/cleanup behavior.
- Lease lifetime spanning SQLite connection open/use/close and verification.
- Native Windows API ABI, access masks, handle ownership, and error translation.
- The Linux POSIX-lock-preserving verification path insofar as B2 changes it.

### Out of scope

- Authentication, authorization, approval reservation, TOTP, worker dispatch, process containment policy beyond its existing independent tests, package-manager behavior, installer invocation, and real software installation.
- Protection against a fully compromised Windows kernel, malicious administrator/SYSTEM, offline disk access by an attacker with equivalent physical/administrative privileges, or malware already executing with the target user's unrestricted token.
- Network shares, mapped drives, removable media, cloud-synced folders, and arbitrary reparse providers; these are rejected rather than supported.

### Trust boundaries

- **Application process ↔ Windows object manager / filesystem:** all native handles, object names, access masks, and security descriptors cross this boundary.
- **Application process ↔ SQLite:** SQLite receives a path only after the adapter has established the protected directory/file set and holds the lease for the connection lifetime.
- **User logon session A ↔ user logon session B:** the global mutex is intended to coordinate processes belonging to the same user SID across sessions. This assumption requires a real two-session acceptance test.
- **Application ↔ local filesystem namespace:** untrusted path components and concurrent rename/replacement attempts must not redirect validated handles to a different object.

## 3. Adversaries and assumptions

### Considered adversaries

- A same-machine, unprivileged process running under a different user SID that attempts to read, replace, rename, or weaken the protected state.
- A process running as the same user that races directory/file creation, uses alternate path spellings (including 8.3 aliases), or starts a second store instance.
- A concurrent process that attempts to rename an ancestor while the lease is held.
- A malformed or unexpected Windows security descriptor/ACE representation returned by the native security APIs.
- A process in another logon session for the same user that opens the same store concurrently.
- Environmental failures such as unsupported filesystem behavior, native API failure, access denied, mutex timeout, or missing sidecar files.

### Assumptions requiring validation

- Windows 11 Home supports the exact required `NtCreateFile` relative-open behavior, security descriptor application, handle share semantics, and named global mutex access masks used by the adapter.
- The ctypes structure layouts, signed NTSTATUS handling, pointer widths, API prototypes, and handle conversions match the target Python and Windows ABI.
- A global mutex with the specified DACL is visible and usable by the same user SID across two independent logon sessions, without unintended access by other users.
- The filesystem is a supported fixed local volume with stable volume serial and file ID semantics.
- The process token SID used by the adapter is the intended user identity. Elevation, impersonation, service identities, and unusual token configurations must be explicitly tested or rejected.

These assumptions are not considered proven by mocked unit tests or GitHub-hosted CI alone.

## 4. Threat analysis (STRIDE)

| Threat | Security impact | Current control / evidence | Residual gate |
|---|---|---|---|
| Spoofing: substitute a path component after validation | Open or create the database in an attacker-controlled directory | Pin ancestor handles; open/create the dedicated child relative to a pinned parent; reject reparse points; verify returned handle | Independent review of native object attributes and target-machine race behavior |
| Spoofing: use long/short path aliases to obtain a different mutex | Two processes bypass serialization | Mutex key derives from validated directory handle volume serial + file ID, not path spelling | Native 8.3 alias test on a volume where aliases are enabled |
| Tampering: replace database or sidecar with a reparse point | Redirect SQLite I/O or expose data | Pre-create/open and verify database, WAL, SHM, journal entries; reject reparse attributes | Execute native database and each sidecar reparse-point fixtures on Windows 11 Home |
| Tampering: weaken DACL or use wrong owner | Unauthorized read/write or persistence | Require current-user owner, protected DACL, exactly one expected allow ACE; reject unsupported ACE shapes; never repair existing ACLs | Validate wrong-owner, Everyone/broad ACE, inherited/unprotected and malformed ACE fixtures natively |
| Tampering: rename an ancestor while lease is held | Break path-to-handle assumptions or redirect later opens | Ancestor handles request directory-list access and omit share-delete; integration test attempts higher-ancestor rename | Independent review of share modes/access masks and actual NTFS behavior |
| Repudiation / ambiguous commit: commit succeeds but verification fails | Caller may retry a committed operation and duplicate state transition | Raise `JobStoreCommittedButUnverified`; provide owner-scoped persisted-version lookup for reconciliation | Verify caller reconciliation paths and ensure no blind retry remains |
| Information disclosure: broad/inherited ACL or default token owner | Other principals read SQLite files | Explicit protected owner-only DACL and owner verification for directory and each file-set entry | Review exact SDDL, ACE semantics, inheritance flags and elevated-token behavior |
| Denial of service: mutex held or abandoned | Store cannot initialize or make progress | Bounded five-second wait; accept normal/abandoned ownership results; close handle and release only if acquired | Two-session contention, timeout, abandoned-owner and cleanup tests |
| Elevation / unauthorized mutex access | Another principal acquires or manipulates global mutex | Global object with explicit protected DACL granting mutex-all-access only to current SID and LocalSystem | Verify object namespace, mandatory integrity label, DACL behavior and cross-session access on target Windows |
| Denial of service: native API or ACL parser behavior differs | Storage may be unavailable or behave unexpectedly | Fail-closed translation for native errors and unsupported ACE tuple forms | Independent ABI/interop review and Windows 11 Home acceptance |

## 5. Required invariants

The following invariants must hold for every successful Windows lease:

1. The path is absolute and on a fixed local drive.
2. Every existing ancestor from the volume root to the parent of the dedicated state directory is pinned as a directory and is not a reparse point.
3. The dedicated state directory is created/opened relative to the pinned parent and the returned handle is verified as a non-reparse directory.
4. The state directory owner is the current user SID; its DACL is protected and contains exactly the required owner-only allow ACE.
5. The global mutex key is derived from the verified directory handle identity and the current user SID; mutex acquisition happens before the SQLite file set is opened/created.
6. The global mutex DACL is protected and grants the required access only to the current user SID and LocalSystem.
7. Database and sidecar entries are regular files, owned by the current user SID, and have the required protected owner-only DACL before SQLite connects.
8. The adapter does not silently repair unsafe existing entries or fall back to weaker storage.
9. The lease remains held until the SQLite connection has closed; verification runs before yielding and after the caller's use.
10. Any failed acquisition, verification, release, or native API operation fails closed and cleans up every acquired native handle exactly once.

## 6. Required acceptance evidence

### Automated evidence

- Exact-head backend, frontend, Playwright/build, and Windows Process Containment workflows.
- Windows tests for state-directory and higher-ancestor rename exclusion.
- Windows tests for database/sidecar and ancestor reparse-point rejection.
- Wrong-owner and broad/untrusted DACL rejection without ACL repair.
- Global mutex SDDL, timeout, release/close, same-path serialization, and long/short alias serialization tests.
- Linux second-process regression proving verification of an active WAL sidecar does not release an existing POSIX lock.
- WAL-mode enforcement and owner-scoped committed-version reconciliation tests.

### Native target acceptance

- Run on the target Windows 11 Home machine with the exact PR head and record OS build, Python version/architecture, filesystem/volume type, and test commit.
- Run all native ACL, owner, reparse, handle lifetime, rename, mutex timeout, alias, and cleanup cases.
- Run a cross-logon-session mutex test: acquire/hold from session A, attempt acquisition from session B using the same user SID, prove B cannot enter during A's hold, then prove B can acquire after A releases. Record session identity and timestamps without recording secrets.
- Collect machine-readable PASS/FAIL output and logs. Any skipped or unsupported mandatory case is a blocker, not a pass.

## 7. Fail-closed and release decision

Windows production storage must remain disabled until all of the following are true:

- Independent reviewer signs off the Windows native API/ABI, ACL, mutex, and handle-lifetime design.
- This threat model has been reviewed and approved by someone other than its author/implementer.
- All exact-head CI workflows pass.
- Required native target acceptance passes on Windows 11 Home.
- The two-logon-session mutex test passes.
- No unresolved security review finding remains.

This document is an engineering threat-model draft. Its existence does not satisfy the independent-review gate. PR #169 remains Draft and unmerged; no worker execution, installer invocation, or real installation is authorized by B2.
