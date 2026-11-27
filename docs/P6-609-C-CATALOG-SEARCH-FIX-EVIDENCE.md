# P6-609-C Catalog Search Fix Evidence

## Problem
A natural-language install request for `DBeaver Community` reached the structured `software.install` intent correctly, but the WinGet source2 catalog search returned no candidates. The catalog query used the entire phrase as one contiguous substring. The catalog's display name is `DBeaver Community Edition` and its package ID is `DBeaver.DBeaver.Community`, so the space-separated phrase did not occur contiguously in either field.

## Change
- Tokenize the validated query into distinct Unicode word tokens.
- Require every token to match at least one of the Microsoft catalog's `name`, `id`, or `moniker` fields.
- Keep all search values parameter-bound; only the count of SQL predicates is assembled from the bounded token list.
- Preserve the existing exact-name/package-ID and name-prefix ranking.
- Keep Microsoft source2 as the only package identity source. Gemini still cannot supply trusted Package IDs, installer URLs, hashes, or commands.

## Regression coverage
- `DBeaver Community` resolves only `DBeaver.DBeaver.Community`.
- Search is case-insensitive and independent of word order.
- Every query word is required, preventing broad partial matches (for example, `DBeaver Enterprise` resolves the Enterprise package, not Community).

## Safety and verification status
- No WinGet command or installer was invoked.
- No TOTP approval, release authorization, worker execution, or live installation was performed.
- Automated regression tests were added. CI results must be checked on the resulting PR head before declaring the fix verified.
- PR #170 remains Draft and unmerged.


## Follow-up: Windows SQLite state-directory ACL startup failure

### Observed failure
On the nominated Windows profile, `%LOCALAPPDATA%\AI-Agent-PC-Automation` had an inherited DACL (SYSTEM, Administrators, and the current user) and `DaclProtected=False`. The Windows SQLite adapter correctly rejected this shared state-root ACL because it requires a protected, explicit owner-only DACL for the database directory. The existing `authenticator` child was already protected and owner-only; the `acceptance` child still inherited the root ACL.

### Fix
- Move only the default install-worker SQLite database to a dedicated sibling directory: `%LOCALAPPDATA%\AI-Agent-PC-Automation-Jobs\jobs.sqlite3` (repository fallback: `.agent-state-Jobs/jobs.sqlite3`).
- Let the existing Windows secure-storage adapter create/open that dedicated directory with its existing explicit owner-only protected DACL and file/sidecar checks.
- Preserve explicit `JOB_STORE_PATH` overrides unchanged; they remain subject to the same strict adapter checks.
- Do not rewrite the shared state-root ACL or touch the existing `acceptance` and `authenticator` directories. The sibling layout also lets the adapter create its dedicated directory on a fresh profile because its parent (`LOCALAPPDATA`) already exists.

### Safety boundary
This is a path-isolation correction only. It does not weaken DACL validation, repair existing untrusted paths, change Approval/TOTP semantics, enable the worker, authorize Real Install, or execute WinGet. The prior root-level `jobs.sqlite3` is not migrated or deleted by this change.

### Verification
Configuration regression tests cover the new default path and preservation of explicit overrides. Windows CI and the target-machine startup check must pass before this issue is considered resolved. PR #170 remains Draft and unmerged.