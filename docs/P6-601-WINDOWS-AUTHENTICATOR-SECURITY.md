# P6-601 Windows Authenticator Storage and Recovery

## Security model

- Google OIDC remains the primary sign-in mechanism.
- TOTP is a Step-up factor for high-risk approvals; it is not required for ordinary sign-in, Dashboard access, or read-only Job Status.
- Google does not support a forced reauthentication request through `prompt=login` or `max_age=0`. The dedicated enrollment/recovery transaction requests the essential `auth_time` ID-token claim; the backend accepts it only when the actual Google authentication time is within the five-minute freshness window and binds it to the one-time OIDC transaction. `prompt=select_account` is used only to select the account and is not treated as freshness evidence.
- If Google returns a stale `auth_time`, the owner must complete a fresh Google sign-in outside this app (for example, after signing out of the Google account in the browser) and retry. The app rejects stale or missing evidence; account selection or consent alone never satisfies the requirement.
- Before relying on enrollment/recovery, the Google Auth Platform project must be **In production**, its Verification status must be **Verified**, and Settings → Advanced Settings → **Session age claims** must be enabled for the OAuth client. Google documents all three as prerequisites for receiving `auth_time`.
- The resulting session has a five-minute, one-use fresh-authentication grant. Enrollment/recovery consumes that grant atomically. Session rotation does not renew it.

## Enrollment

1. The owner starts Google reauthentication from the authenticated Dashboard.
2. The frontend starts a dedicated fresh Google OIDC transaction through `GET /api/auth/google/reauth/start`.
3. The OIDC callback validates fresh-authentication evidence and updates the authenticated session.
4. The owner starts enrollment through `POST /api/authenticator/enrollment`; the backend consumes the one-use fresh-authentication grant and creates a short-lived, owner-bound QR enrollment.
5. The owner scans the QR and confirms with a valid TOTP.
6. Only after confirmation does the backend persist the secret and attempt to rotate the session.

## Lost or unusable TOTP

- The owner can start replacement using fresh Google OIDC authentication; the old TOTP is not required.
- The new QR is pending and memory-only. The existing secret remains active until the new TOTP is confirmed.
- The replacement is bound to the same verified Google owner and has the same short expiry and failed-attempt limit as enrollment.
- On successful confirmation, the new encrypted secret replaces the old file with `MoveFileExW(MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)`; the destination is reopened and its exact payload is verified.
- The source and destination are verified through handles before replacement. Every ancestor directory and the dedicated authenticator state directory remain pinned without `FILE_SHARE_DELETE` while the full-path rename runs. The leaf replacement uses the Win32 path-based rename API because the prior handle-based `FileRenameInfo` implementation reported success on the hosted Windows runner while leaving the old destination payload in place. The dedicated directory has an owner-only DACL; same-user processes remain outside the threat boundary.
- The temporary file contents are flushed with `FlushFileBuffers` before rename. `MOVEFILE_WRITE_THROUGH` requests that the move operation complete after the move is flushed to disk.
- If replacement fails before the rename completes, the old secret remains. A failed or abandoned QR does not disable ordinary Google sign-in.
- This recovery route depends on the primary Google account. It is not an offline Google-account recovery mechanism.

## Windows secret-file protection

The default secret file is `.agent-state/authenticator/authenticator.json` under the repository root. Leave `AUTHENTICATOR_SECRET_PATH` blank to use that default; any override must be a direct child of the same dedicated `.agent-state/authenticator` directory. The application rejects paths elsewhere rather than changing the DACL of a potentially shared folder. Existing encrypted secrets at the previous default path `.agent-state/authenticator.json` are not migrated or copied. Owners upgrading from that default must re-enroll before Step-up can succeed. Existing local `.env` overrides that point to the old path must be updated before starting this version; do not copy plaintext secrets or weaken ACL checks.

The Windows adapter uses pywin32 and fails closed if the required security APIs are unavailable.

- Resolves the current process token's user SID.
- Creates the dedicated application-owned directory `.agent-state/authenticator` and secret file with exclusive creation. Configuration rejects secret paths outside this dedicated directory; the adapter never applies a DACL to an arbitrary configured/shared parent directory.
- Sets and verifies the owner SID on newly created state paths.
- Applies a protected DACL with exactly one allow ACE: current user SID, full file access, no inherited ACEs.
- Verifies owner SID on every open. If the owner is already the current user, the adapter repairs an overly broad or inherited DACL on the final state directory. It never takes ownership of an existing directory or file.
- For an existing secret file, the adapter first verifies the owner SID on the already-opened handle. If the owner is the current user, it repairs the DACL to the exact protected owner-only form and verifies the result. It never takes ownership of an existing file. A wrong-owner file is rejected.
- Verifies the repaired directory DACL and protected-DACL control bit before reading or writing.
- Opens every path component with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects reparse points, and keeps directory handles open without `FILE_SHARE_DELETE` while operating on the secret.
- This intentionally rejects every reparse point in the ancestor chain, including cloud-sync placeholder directories such as OneDrive. Keep the repository in a local, non-synced directory; this is a fail-closed availability limitation, not a fallback to weaker path validation.
- Opens the secret itself without delete sharing and without concurrent write sharing; reads and writes use the verified file handle.
- Replacement creates a new protected file in the dedicated directory, verifies source and destination through handles, then uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH` while all verified parent-directory handles remain open without `FILE_SHARE_DELETE`. It reopens the destination and verifies the exact payload. The leaf rename is path-based; the owner-only directory and same-user-malware exclusion define that boundary.
- DPAPI remains current-user scoped; the file ACL is an additional access-control boundary, not a replacement for DPAPI.

## Failure behavior and recovery limitations

- If the encrypted secret cannot be read, the Google-authenticated session remains valid and the API reports authenticator storage unavailable.
- The Dashboard and read-only Job Status remain accessible. The UI offers a Google-reauthenticated recovery attempt even when the secret payload is corrupt.
- A current-user-owned final state directory or secret file with a bad DACL is hardened through its verified handle before use. A wrong-owner path remains rejected; the adapter never takes ownership of an existing path.
- Wrong-owner and reparse-point paths remain rejected.
- A current-user-owned secret file with a bad DACL may be repaired through its already-verified handle. A wrong-owner file or a DACL that cannot be repaired is rejected; recovery never takes ownership of an existing file.
- A confirmed replacement can replace a corrupt encrypted payload only when the existing secret file passes those owner/DACL trust checks. Recovery cannot replace a file whose owner or ACL trust cannot be established.
- Enrollment, Step-up, and other high-risk operations fail closed while authenticator storage is unavailable.
- If replacement fails, the adapter attempts to delete its randomly named temporary file while the verified parent directory remains pinned. If cleanup itself fails, the leftover file is inert DPAPI ciphertext in the owner-only directory and must be removed only through a verified maintenance procedure.
- No fallback to an unprotected file, another user's SID, or disabled authentication is permitted.

## Scope and remaining gates

- Windows is the first supported platform for this storage adapter.
- The SQLite Job Store's separate Windows DACL/handle gate is not changed by this work.
- This work does not connect Approval to a worker, invoke WinGet, execute an installer, or mutate the host.
- CI and Windows hosted-runner tests are necessary but do not replace independent A4 review or acceptance on the target Windows 11 Home machine.
- Same-user malware and a fully compromised Windows account remain outside the protection boundary: processes running as the same user can use that user's DPAPI context.
