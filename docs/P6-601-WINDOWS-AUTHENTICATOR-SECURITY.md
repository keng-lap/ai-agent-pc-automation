# P6-601 Windows Authenticator Storage and Recovery

## Security model

- Google OIDC remains the primary sign-in mechanism.
- TOTP is a Step-up factor for high-risk approvals; it is not required for ordinary sign-in, Dashboard access, or read-only Job Status.
- Ordinary Google sign-in does not force a password prompt. A dedicated reauthentication transaction uses `prompt=login` and `max_age=0` only for authenticator enrollment or replacement.
- The backend validates the fresh-authentication claim from the OIDC ID token and binds it to the one-time OIDC transaction.
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
- On successful confirmation, the new encrypted secret replaces the old file using a single Windows file-rename operation; the destination is reopened and verified.
- The temporary file is opened with `FILE_FLAG_WRITE_THROUGH` and its contents are flushed with `FlushFileBuffers` before handle-based rename. The rename remains handle-based to preserve the verified-object boundary. The Win32 handle-based rename used here has no documented write-through rename flag, and this implementation does not flush parent-directory metadata. Therefore, atomic namespace replacement is intended, but crash/power-loss durability of the directory entry is not guaranteed; this is a documented residual limitation, not a durability guarantee.
- If replacement fails before the rename completes, the old secret remains. A failed or abandoned QR does not disable ordinary Google sign-in.
- This recovery route depends on the primary Google account. It is not an offline Google-account recovery mechanism.

## Windows secret-file protection

The Windows adapter uses pywin32 and fails closed if the required security APIs are unavailable.

- Resolves the current process token's user SID.
- Creates the application state directory and secret file with exclusive creation.
- Sets and verifies the owner SID on newly created state paths.
- Applies a protected DACL with exactly one allow ACE: current user SID, full file access, no inherited ACEs.
- Verifies owner SID on every open. If the owner is already the current user, the adapter repairs an overly broad or inherited DACL on the final state directory. It never takes ownership of an existing directory or file.
- For an existing secret file, the adapter first verifies the owner SID on the already-opened handle. If the owner is the current user, it repairs the DACL to the exact protected owner-only form and verifies the result. It never takes ownership of an existing file. A wrong-owner file is rejected.
- Verifies the repaired directory DACL and protected-DACL control bit before reading or writing.
- Opens every path component with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects reparse points, and keeps directory handles open without `FILE_SHARE_DELETE` while operating on the secret.
- Opens the secret itself without delete sharing and without concurrent write sharing; reads and writes use the verified file handle.
- Replacement creates a new protected file in the same secured directory and uses `SetFileInformationByHandle(FileRenameInfo)` with replacement enabled, then reopens and verifies the destination. The current implementation does not provide an explicit write-through rename guarantee.
- DPAPI remains current-user scoped; the file ACL is an additional access-control boundary, not a replacement for DPAPI.

## Failure behavior and recovery limitations

- If the encrypted secret cannot be read, the Google-authenticated session remains valid and the API reports authenticator storage unavailable.
- The Dashboard and read-only Job Status remain accessible. The UI offers a Google-reauthenticated recovery attempt even when the secret payload is corrupt.
- A current-user-owned final state directory or secret file with a bad DACL is hardened through its verified handle before use. A wrong-owner path remains rejected; the adapter never takes ownership of an existing path.
- Wrong-owner and reparse-point paths remain rejected.
- A confirmed replacement can replace a corrupt encrypted payload only when the existing secret file passes owner/DACL trust checks. It cannot repair an untrusted file ACL.
- Enrollment, Step-up, and other high-risk operations fail closed while authenticator storage is unavailable.
- Failed replacement can leave a randomly named temporary file in the protected directory. The current implementation has no automated cleanup/maintenance pass; cleanup is a manual maintenance task and must not use an unverified path.
- No fallback to an unprotected file, another user's SID, or disabled authentication is permitted.

## Scope and remaining gates

- Windows is the first supported platform for this storage adapter.
- The SQLite Job Store's separate Windows DACL/handle gate is not changed by this work.
- This work does not connect Approval to a worker, invoke WinGet, execute an installer, or mutate the host.
- CI and Windows hosted-runner tests are necessary but do not replace independent A4 review or acceptance on the target Windows 11 Home machine.
- Same-user malware and a fully compromised Windows account remain outside the protection boundary: processes running as the same user can use that user's DPAPI context.
