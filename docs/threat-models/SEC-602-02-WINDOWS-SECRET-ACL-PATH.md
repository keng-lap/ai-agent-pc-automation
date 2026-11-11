# Threat Model — SEC-602-02 Windows Secret File ACL & Path Hardening

- **Status:** Draft — implementation design and Windows validation required
- **Author:** AI-assisted engineering draft
- **Reviewer:** Pending independent security review
- **Date:** 2026-11-10
- **Base commit:** 9229f8d764919a0d5e752c81a922f56065681de7
- **Scope:** `EncryptedTotpSecretFileStore` secret-file creation, loading, path handling, Windows ACLs, reparse-point handling, and native-handle lifetime.
- **Applicable decisions / phase documents:** `docs/PHASE-6.md`, `docs/SECURE-DEVELOPMENT-STANDARD.md`, applicable SEC-602 remediation plan and authenticator design decisions.

## 1. Intended behavior and non-goals

Protect the authenticator secret file against access by unintended local principals and prevent path substitution/reparse-point races during create, read, and write operations. On Windows, enforce and verify the intended DACL using Windows security APIs rather than relying on POSIX mode bits.

Non-goals:
- Do not change ACLs recursively or silently on arbitrary user-configured parent directories.
- Do not change authentication, TOTP, DPAPI envelope format, or enrollment semantics except where required for safe file access.
- Do not add network access, cloud storage, or new persistence.
- Do not inspect or modify the user's live PC during development or tests.
- Do not enable real machine-changing capabilities.

## 2. Assets and security objectives

| Asset | Why it matters | Required protection |
|---|---|---|
| TOTP secret ciphertext/envelope | Supports account second factor | Confidentiality and integrity; restrictive file access |
| Secret-file path and parent directory | Controls which object is opened | Canonical, bounded, non-ambiguous path; reject unsafe reparse traversal |
| Windows file handle | Represents the object actually accessed | Validate handle security and use same handle for I/O |
| DACL/owner metadata | Determines local access | Explicit least-privilege policy; verify actual descriptor |
| DPAPI-protected payload | Protects secret at rest | Preserve existing cryptographic contract and error behavior |

## 3. Actors and trust boundaries

| Actor/component | Trust level | Inputs/outputs | Boundary controls |
|---|---|---|---|
| Local authenticated application | Trusted only within backend policy | Secret-store calls | Fixed code path, no caller-selected native flags |
| Local interactive user | Authorized owner, not assumed to be sole local principal | Configures path and runs application | Explicit path policy and ownership checks |
| Other local Windows principals/processes | Untrusted | May attempt file access or path replacement | Restrictive DACL, handle-based checks, reparse protections |
| Filesystem / parent directory | Mutable shared state unless proven private | Paths, directory entries, reparse points | Avoid check-then-open; validate opened handles |
| Environment/configuration | Untrusted configuration input | `AUTHENTICATOR_SECRET_PATH` | Parse, normalize, bound, and apply explicit custom-path policy |
| Windows security APIs | Platform authority | Handles, security descriptors, attributes | Correct ctypes signatures, error checking, cleanup, Windows CI |

## 4. Data-flow trace

Configuration path -> path parsing/normalization -> parent-directory policy -> native file open/create with reparse protections -> validate opened object attributes and security descriptor -> read/write through the validated handle -> close handle on every path.

No security decision may rely solely on a pre-open `Path.is_symlink()`, `exists()`, or `is_file()` check. No read/write operation may reopen the path after validating a different handle.

## 5. Threats and abuse cases

| ID | Threat / abuse case | Preconditions | Impact | Mitigation / invariant | Test ID | Residual risk |
|---|---|---|---|---|---|---|
| T-01 | POSIX mode `0600` assumed to secure Windows file | Store uses `os.open(..., 0o600)` on Windows | Other local principals may obtain access under inherited/default DACL | Explicitly set and verify least-privilege Windows DACL | W-ACL-01.. | Windows ACL semantics require native CI evidence |
| T-02 | Reparse-point or symlink substitution between check and open | Attacker can mutate a path component or directory entry | Secret file redirected to unintended object | Open with reparse-point protections; validate handle and use same handle for I/O | W-PATH-01.. | Parent path components and mount points need defined policy |
| T-03 | Custom path points into shared/untrusted directory | User configures `AUTHENTICATOR_SECRET_PATH` under a shared parent | ACL hardening could expose or damage unrelated data; attacker may replace entry | Do not silently rewrite arbitrary parent ACLs; define explicit custom-path policy and fail closed when requirements unmet | W-CFG-01.. | User-selected path may be unusable until moved to dedicated directory |
| T-04 | File DACL is permissive through inheritance or owner ambiguity | File created under inherited ACL | Secret ciphertext exposed to unintended principals | Use protected DACL and verify effective descriptor/owner against explicit policy | W-ACL-02.. | Exact owner/SYSTEM policy needs reviewer confirmation |
| T-05 | Validated handle is discarded and path reopened | Implementation validates then uses Path.read_text/open | TOCTOU race remains | Perform all I/O using the same validated native handle | W-HANDLE-01.. | Native handle conversion must be audited |
| T-06 | Native handle or security descriptor leaks on exceptions | API call or conversion fails mid-operation | Resource exhaustion or security-state inconsistency | Single ownership model and finally-based cleanup | W-RES-01.. | Mock tests cannot fully prove OS resource behavior |
| T-07 | Incorrect ctypes declarations or error handling | Native API signatures/last-error handling wrong | Memory corruption, false success, or bypass | Explicit argtypes/restype, WinError checks, narrow wrappers, Windows integration tests | W-API-01.. | Test on supported Windows/Python versions |

## 6. Security invariants

- A secret file MUST NOT be created or read with a permissive or unverified Windows DACL.
- The implementation MUST NOT treat POSIX mode bits as proof of Windows access control.
- A reparse-point object at the final secret-file path MUST be rejected.
- A path check performed before opening MUST NOT be treated as proof of the identity or safety of the opened object.
- The handle whose attributes and security descriptor are validated MUST be the same handle used for all I/O.
- Every native handle and allocated security descriptor MUST be released exactly once on all success and failure paths.
- A custom path MUST NOT cause ACL changes to an arbitrary existing parent directory without an explicit policy and ownership check.
- Any inability to establish the required ACL, object identity, or handle safety MUST fail closed; it MUST NOT fall back to weaker Path-based I/O.
- Non-Windows behavior MUST remain explicit and covered by portable tests without pretending to prove Windows security behavior.

## 7. Design decisions

| Decision | Chosen design | Alternatives rejected | Reason |
|---|---|---|---|
| Windows ACL enforcement | **Decision A:** protected DACL grants access only to the SID of the Windows user running the agent; verify owner and effective DACL from the opened handle | Grant SYSTEM or Administrators an explicit ACE; rely on inherited defaults or `0o600` | Least privilege; no additional principal is required for the current interactive, per-user local agent |
| Path access | Pending native API design; open/validate/use same handle | `is_symlink()` then `Path.open()` | Check-then-open race |
| Parent directory | Do not silently modify arbitrary custom parent ACLs | Recursively harden configured parent | Could change access to unrelated user data |
| Fallback behavior | Fail closed when native guarantees cannot be established | Fallback to ordinary pathlib I/O | Would bypass security invariant |

## 8. Verification plan

| Test ID | Positive / negative / boundary / failure | Expected result | Evidence / runner |
|---|---|---|---|
| W-ACL-01 | Create new secret file on Windows | Effective DACL matches documented least-privilege policy | Windows CI |
| W-ACL-02 | Existing file with permissive/inherited DACL | Reject or safely remediate only under approved policy; never silently accept | Windows CI |
| W-PATH-01 | Final path is symlink/reparse point | Reject without reading/writing target | Windows CI |
| W-PATH-02 | Replace path between resolution and open | Opened handle validation detects/rejects substitution | Windows race test on Windows CI |
| W-HANDLE-01 | Validate handle then perform read/write | I/O occurs through same handle; no path reopen | Unit spy + Windows integration |
| W-CFG-01 | Custom parent is shared/unowned/unsafe | Fail closed without changing unrelated parent ACL | Windows CI with temporary fixture |
| W-RES-01 | Inject failures after each native allocation/open | Every handle/allocation released exactly once | Fake API unit tests |
| W-API-01 | Native API returns failure | Correct WinError surfaced internally; no permissive fallback | Fake API + Windows CI |
| W-PORT-01 | Non-Windows store tests | Existing portable behavior preserved; Windows guarantees not claimed | Linux CI |

Include zero-I/O assertions when a path or ACL validation fails. All fixtures must be isolated temporary directories; do not use the user's real authenticator file.

## 9. Privacy, logging, and retention

Do not log secret bytes, ciphertext, DPAPI blobs, raw security descriptors, or secret-bearing exception data. Log only minimal operation outcome and sanitized error category. Do not add new persistent data.

## 10. Residual risks and decisions required

- **Product Owner decision (2026-11-11): A — only the current Windows user SID that runs the agent is authorized.** Do not add SYSTEM, Administrators, or broad groups to the file DACL. The implementation must derive the SID from the process token; it must not accept a caller-supplied SID.
- Verify the file owner and effective DACL from the same native handle used for I/O. Require a protected DACL with only the current-user allow ACE; reject unexpected allow or deny ACEs rather than silently broadening access.
- If a future Windows service or SYSTEM-run agent is required, treat it as a new security design and obtain a separate Product Owner decision; do not silently add SYSTEM now.
- Parent-directory guarantees for custom `AUTHENTICATOR_SECRET_PATH` values need an explicit fail-closed policy.
- Windows reparse-point handling for every parent component, including junctions/mount points, must be specified and tested.
- Native API implementation requires Windows CI evidence; mocks alone are insufficient.

## 11. Review disposition

- [x] Scope and source-of-truth decisions reconciled (current-user SID only; Product Owner decision A)
- [ ] Trust boundaries and data flow reviewed
- [ ] Threats and abuse cases covered
- [ ] Security invariants are testable
- [ ] Negative tests are defined
- [ ] Platform-specific evidence is identified
- **Disposition:** BLOCKED pending native implementation, Windows CI evidence, and independent review
- **Reviewer rationale:** Draft threat model only. No implementation authorization is implied by this document.
