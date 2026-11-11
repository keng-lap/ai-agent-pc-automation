# Security Decision — SEC-602-02 Windows Secret File ACL

- **Decision:** A — current Windows user SID only
- **Date:** 2026-11-11
- **Scope:** The DPAPI-protected TOTP authenticator file used by the interactive, local-first agent.
- **Status:** Product Owner decision recorded; implementation and independent A4 review pending.

## Decision

The file DACL must grant the minimum required access only to the SID of the Windows user account running the agent.

Do not add explicit access entries for:
- SYSTEM
- BUILTIN\Administrators
- BUILTIN\Users
- Authenticated Users
- Everyone
- Any caller-supplied or configuration-supplied SID

The file owner must be the current user. The DACL must be protected from parent inheritance and verified from the actual opened file handle. Any unexpected ACE, owner mismatch, or inability to verify the descriptor causes a fail-closed error.

## Implementation constraints

1. Derive the user SID from the process token using Windows APIs. Never trust a SID passed through API input or environment configuration.
2. Create/open the file with an explicit security descriptor. Do not treat POSIX mode `0o600` as Windows access control.
3. Read back and validate owner and DACL on the same handle used for file I/O.
4. Reject reparse points and path substitution. Do not rely on pre-open `Path.is_symlink()` or `exists()` checks.
5. Do not recursively change ACLs on arbitrary parent directories. The configured parent must satisfy a documented trusted-directory policy; otherwise fail closed without modifying unrelated data.
6. Keep DPAPI current-user protection. This DACL decision does not protect against compromise of the same logged-in Windows account, malware running as that user, or an administrator able to take ownership/change ACLs.
7. No Windows service, SYSTEM execution, multi-user sharing, or remote access is authorized by this decision.

## Required evidence before acceptance

- Windows CI verifies the exact owner SID and protected DACL.
- Negative tests reject extra allow/deny ACEs, wrong owner, inherited permissive ACLs, final reparse points, and unsafe parent paths.
- Failure-injection tests prove handles and security-descriptor allocations are released.
- Tests prove no fallback to ordinary pathlib I/O after a native API failure.
- Independent A4 review confirms the native API signatures, handle lifetime, path/reparse behavior, and same-handle I/O.

## Revisit trigger

If the product changes to a Windows service, runs under SYSTEM, supports multiple Windows users, or requires administrator-managed access, create a new threat model and obtain a separate explicit decision. Do not amend this policy implicitly.
