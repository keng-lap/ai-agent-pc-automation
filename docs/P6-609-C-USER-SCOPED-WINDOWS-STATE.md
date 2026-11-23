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
