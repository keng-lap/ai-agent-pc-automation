# P6-609-C — Per-Windows-User Local State

## Decision

The default Windows state root is:

`%LOCALAPPDATA%\AI-Agent-PC-Automation\`

The root is resolved from the environment of the Windows account running the backend. It is not derived from the repository checkout path and does not contain a hard-coded account name or SID.

Default files:

- `jobs.sqlite3` — durable install queue and audit events.
- `authenticator\authenticator.json` — DPAPI-protected TOTP secret.
- `winget-work\` — temporary installer staging/work directory.

Each Windows account therefore gets a distinct state root. Windows secure-storage adapters continue to obtain the current process TokenUser SID at runtime and require owner-only, protected ACLs. The application does not require an elevated Administrator process for normal operation.

## Security properties

- No account SID, username, profile path, or machine identity is hard-coded.
- A different Windows user gets a different `LOCALAPPDATA` root and a different DPAPI user scope.
- SQLite state and TOTP secret remain local to the Windows account. They are not shared between accounts or machines.
- Explicit `JOB_STORE_PATH` and `AUTHENTICATOR_SECRET_PATH` overrides remain subject to existing strict path, owner, DACL, and reparse-point checks. An override does not bypass the security adapters.
- Existing state with an unexpected owner or ACL is not silently taken over, repaired, deleted, or imported.

## Existing development checkouts

Older development versions defaulted to `.agent-state\` under the repository. This change does not automatically migrate that directory. It remains untouched as a recovery source because it may contain TOTP enrollment material and durable approval/job records.

Before adopting an existing checkout, an explicit migration must preserve the source, verify the current-user DPAPI context for the authenticator, and reconcile queued/claimed jobs without replaying them. Until that migration is completed, do not approve or execute installs from the new state root. A fresh user state root must not be treated as proof that prior TOTP enrollment or pending approvals were migrated.

## Windows validation

The Windows CI suite must verify that:

1. The default state root is under the supplied `LOCALAPPDATA`.
2. Two distinct profile roots resolve to different state roots.
3. SQLite creates the state directory and database with the runtime TokenUser SID and protected owner-only DACLs.
4. The authenticator file uses the same runtime user identity and remains DPAPI user-scoped.
5. A pre-existing directory owned by another SID is rejected without ownership or DACL mutation.

The application must be run as the signed-in standard user for normal use. Administrator elevation is reserved for separately approved maintenance tasks.

## Real WinGet release gate and process lifecycle

Real installation is a supported product capability, but the local worker is not started by default. The release gate requires all of the following at backend startup: `AI_AGENT_ENABLE_REAL_INSTALL=1`, task `P6-609-C`, one exact WinGet package ID and version, a 64-character random nonce, and an offset-aware expiry no more than 15 minutes in the future. Missing, malformed, expired, mismatched, or uncertain authorization fails closed. This release authorization is separate from the authenticated owner session, exact package evidence, one-use TOTP approval, and post-install verification.

Prepare the bounded release authorization from the same PowerShell process that will start/restart the backend:

```powershell
.\scripts\authorize-real-install.ps1 -PackageId "Contoso.Editor" -Version "2.4.1" -ExpiresInMinutes 10
```

Use the exact package ID and version shown in the verified proposal. Then restart the backend from that same PowerShell window. The script does not use `setx` or persist machine-wide environment variables. The nonce is atomically consumed in the protected SQLite store and bound to the exact approval digest; a replay or a different package/version is rejected. Prepare a fresh authorization for each real install. The readiness endpoint reports whether the full authorization is currently valid. To disable live execution, restart the backend without running the authorization script.

EXE candidates are eligible only when the selected Microsoft WinGet manifest declares a bounded `InstallerSwitches.Silent` value. That backend-resolved value is included in immutable approval evidence and the generated local manifest; the client and Gemini cannot supply or override it. EXE installers without a declared silent switch are rejected rather than launched interactively.

The worker consumes the one-use release authorization immediately before the side-effect boundary, then passes a cancellation signal to the contained WinGet executor. Lease-renewal failure or application shutdown signals cancellation; the executor terminates the WinGet Job Object process tree and waits for the process handle before returning. The resulting job outcome is UNKNOWN, not success, and must be reconciled against the exact installed package/version before any later action. An expired lease is also reconciled to UNKNOWN by the durable queue and is never automatically retried.

## Acceptance boundary

CI can validate configuration, queue transitions, and process-control behavior, but it cannot prove a real package install on the target Windows account. Final acceptance still requires an explicitly approved Windows run with WinGet available, valid user-scoped state/DPAPI enrollment, and a selected test package. No real install is performed by CI or by PR review.
