# P6-601 Windows Authenticator Storage and Step-up Security

## Security model

- Google OIDC is the sole primary application sign-in mechanism.
- The existing Authenticator App (TOTP) is a Step-up factor for high-risk approvals. It is not required for ordinary Google sign-in, Dashboard access, or read-only Job Status.
- TOTP enrollment is a one-time trusted-setup flow. The QR material is short-lived, owner-bound, session-bound, memory-only, and is returned only to the authenticated owner.
- **Self-service TOTP recovery and replacement are not implemented.** There are no recovery endpoints, recovery codes, WebAuthn ceremonies, email/SMS fallback, or alternate second-factor bypass. If the enrolled authenticator is lost or its secret storage becomes unavailable, high-risk approvals fail closed. Any future recovery procedure requires a separate Product Owner-approved design and security review.
- Enrollment does not change the Google sign-in session or introduce a second Google authentication ceremony.

## Enrollment and Step-up

1. The owner signs in through the configured Google OIDC Master User account.
2. The owner starts TOTP enrollment from the authenticated Dashboard.
3. The backend creates a short-lived, one-time QR enrollment bound to the authenticated Google owner and current application session.
4. The owner scans the QR with an Authenticator App and confirms with a valid six-digit TOTP.
5. The backend consumes the matching TOTP time-step and persists the protected secret. A pending enrollment cannot be confirmed by a different owner or application session.
6. High-risk approval requires a fresh, exact-action-bound Step-up challenge and a valid TOTP. Approval remains Dry Run only; it does not install software or mutate the host.

## Windows secret-file protection

The default secret file is `.agent-state/authenticator/authenticator.json` under the repository root. Leave `AUTHENTICATOR_SECRET_PATH` blank to use that default; any override must be a direct child of the same dedicated `.agent-state/authenticator` directory. The application rejects paths elsewhere rather than changing the DACL of a potentially shared folder. Existing encrypted secrets at the previous default path `.agent-state/authenticator.json` are not migrated or copied. Owners upgrading from that default must follow the separately documented trusted setup before Step-up can succeed. Do not copy plaintext secrets or weaken ACL checks.

The Windows adapter uses pywin32 and fails closed if the required security APIs are unavailable.

- Resolves the current process token's user SID.
- Creates the dedicated application-owned directory and secret file with exclusive creation.
- Sets and verifies the owner SID on newly created state paths.
- Applies a protected DACL with exactly one allow ACE: current user SID, full file access, no inherited ACEs.
- Verifies owner SID on every open. If the owner is already the current user, the adapter repairs an overly broad or inherited DACL on the final state directory or secret file through the verified handle. It never takes ownership of an existing directory or file.
- Verifies the repaired directory DACL and protected-DACL control bit before reading or writing.
- Opens every path component with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects reparse points, and keeps directory handles open without `FILE_SHARE_DELETE` while operating on the secret.
- This intentionally rejects every reparse point in the ancestor chain, including cloud-sync placeholder directories such as OneDrive. Keep the repository in a local, non-synced directory; this is a fail-closed availability limitation, not a fallback to weaker path validation.
- Opens the secret itself without delete sharing and without concurrent write sharing; reads and writes use the verified file handle.
- DPAPI remains current-user scoped; the file ACL is an additional access-control boundary, not a replacement for DPAPI.

## Failure behavior and limitations

- If the encrypted secret cannot be read, the Google-authenticated session remains valid and the API reports authenticator storage unavailable.
- The Dashboard and read-only Job Status remain accessible. High-risk approvals are blocked while authenticator storage is unavailable or no TOTP is enrolled.
- Wrong-owner and reparse-point paths remain rejected.
- A current-user-owned final state directory or secret file with a bad DACL may be hardened through its verified handle. A wrong-owner path remains rejected; the adapter never takes ownership of an existing path.
- No fallback to an unprotected file, another user's SID, disabled authentication, recovery code, or alternate factor is permitted.
- Same-user malware and a fully compromised Windows account remain outside the protection boundary: processes running as the same user can use that user's DPAPI context and owner-only directory.

## Scope and remaining gates

- Windows is the first supported platform for this storage adapter.
- The SQLite Job Store's separate Windows DACL/handle gate is not changed by this work.
- This work does not connect Approval to a worker, invoke WinGet, execute an installer, or mutate the host.
- CI and Windows hosted-runner tests are necessary but do not replace independent security review or acceptance on the target Windows 11 Home machine.
