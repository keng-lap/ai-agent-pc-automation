# P6-603 — Exact-artifact WinGet adapter foundation

## Status

**Manifest preparation only. Not wired to API dispatch and does not execute WinGet or an installer.**

This change replaces the unsafe assumption that `winget install --id ... --version ...` is bound to the bytes shown in an approval challenge. The adapter now builds a minimal local WinGet manifest from the immutable backend `InstallApprovalBinding`.

## Security decision

The live-source install command is not an acceptable execution path for evidence-bound approval. It resolves package metadata from the configured live source at execution time. The source manifest or installer URL can change after the user approves the original evidence.

The adapter therefore creates a local, three-file manifest using only fields from the immutable approval evidence:

- Exact package identifier and version.
- Exact installer type, architecture, and user scope.
- Exact HTTPS installer URL.
- Exact approved installer SHA-256.
- Display name and publisher from the same evidence record.

Before command arguments can be built, the adapter re-checks evidence freshness and compares every manifest file against a freshly generated expected document. Extra files, symlinks, changed contents, mismatched file extensions, unsupported installer types, and non-user scope are rejected.

The generated manifest intentionally omits arbitrary installer switches, custom commands, dependencies, and scripts. The fixed argument vector uses `winget install --manifest <directory>`, user scope, the approved architecture, silent/non-interactive mode, dependency skipping, and no-upgrade. It does not pass a live source, package ID lookup, `--override`, `--custom`, `--force`, or `--ignore-security-hash`. Package/source agreements are not auto-accepted; if WinGet requires an agreement, installation must stop for explicit user review.

## Important Windows prerequisite

Microsoft documents that installing from local manifest files requires the WinGet `LocalManifestFiles` feature to be enabled by an administrator. The documented command is:

```powershell
winget settings --enable LocalManifestFiles
```

This project must **not** run that command automatically, elevate itself, or change the user's Windows settings silently. Runtime integration must detect the prerequisite and fail closed with a clear setup message. Any one-time administrator setup must be separately explained and explicitly approved by the user.

Reference: https://learn.microsoft.com/en-us/windows/package-manager/winget/install

Microsoft also documents that the manifest's `InstallerSha256` is used to validate downloaded installer bytes. The local manifest binds that hash to the approved evidence rather than trusting a fresh live-source manifest.

Reference: https://learn.microsoft.com/en-us/windows/package-manager/winget/download

## Current boundary

- No WinGet process is started by this module.
- No installer is executed.
- No local Windows setting is inspected or changed.
- No publisher trust anchor is enabled; the evidence registry remains default-deny.
- No approval API, job system, or fixed tool dispatch calls this module.
- DBeaver remains blocked while its package manifest does not match the official publisher release.

## Required gates before execution

1. Add a Windows-specific preflight for the current-user WinGet executable. Verify its resolved executable identity and Microsoft signature against an independently reviewed trust policy; do not trust mere file existence or PATH lookup.
2. Detect whether `LocalManifestFiles` is enabled without changing it. If disabled, return a blocked prerequisite state; never self-enable or elevate.
3. Implement process-tree containment and cancellation semantics. A timeout must not be reported as a clean failure if a child installer may still be running. Prefer a Windows Job Object or an equally strong, tested containment boundary.
4. Keep output bounded while draining stdout/stderr; do not use unbounded `capture_output=True`.
5. Bind a consumed, one-use approval result to the exact `InstallApprovalBinding` and job. The adapter must not accept a bare SHA-256 string or a client-created approval flag.
6. Integrate through a backend-owned fixed handler and the approved Background Job System only after the above gates and independent A4 review pass.
7. Add Windows acceptance tests using a signed, harmless test installer and a test-only package source. Do not use a real user installation as a CI test.
8. Keep third-party signer trust anchors default-deny until each publisher fingerprint is independently verified.

## Test coverage added in this foundation

- Exact URL/hash/version/package identity appear in generated manifest.
- Unsupported installer types and non-user scope are rejected.
- Arbitrary installer switches and command text are not copied into the manifest.
- Arguments use only a local manifest and fixed user-scope flags.
- Expired approval evidence is rejected.
- Symlink work roots are rejected.
- Tampered manifest contents and extra manifest files are rejected.
- Cleanup is limited to a generated directory directly under the fixed work root.

This document records a security foundation, not authorization to install software or enable real execution.


## A4 review — current head 7c669c6140228ca7e25515983981377ebf8e0237

**No Critical finding in this manifest-preparation-only module. This is not an execution approval.** The module has no process invocation or installer dispatch. The following High execution blockers remain and must be closed before any call to WinGet:

1. **Manifest TOCTOU — helper implemented; execution integration still gated:** `lock_prepared_manifest` now opens the manifest directory and all three files with Windows sharing that allows read access only, then revalidates the exact approval-bound contents while the handles remain open. The future WinGet process must run entirely inside this context. Calling `build_install_arguments` and launching WinGet after the context exits is unsafe. Windows tests verify write and delete attempts fail while the lock context is active.
2. **WinGet executable identity:** the current-user alias must be resolved and the actual executable verified with a reviewed Microsoft signer policy. File existence, PATH resolution, and an unpinned subject string are insufficient.
3. **LocalManifestFiles prerequisite:** Microsoft documents this as an administrator-controlled setting. Runtime must not self-enable or elevate. If state cannot be read reliably without PowerShell or another prohibited execution path, fail closed and present the one-time setup requirement to the user.
4. **Process lifecycle:** no process-tree containment, cancellation, bounded output-draining, or orphan-installer reconciliation exists. A timeout must produce an explicit unknown outcome until the job can prove no installer remains active.
5. **Installer silent semantics:** this manifest intentionally omits package-provided switches. A package that cannot use WinGet's default silent behavior must be marked unsupported until its exact package-specific switch contract is independently reviewed and included in the approval digest.
6. **Post-install verification:** no package identity/version/scope verification exists. Exit code zero alone must not be treated as proof that the intended user-scope package is installed.

### CI evidence for this head

- Backend: 461 passed, 2 skipped.
- Ruff: passed.
- Frontend unit tests, Playwright desktop/mobile E2E, and production build: passed.
- CodeQL Python, JavaScript/TypeScript, and Actions analyses: passed.
- CI run: https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43238500610
- CodeQL run: https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43238492339

These checks validate the current code and existing regression suite. They do not provide Windows WinGet local-manifest execution acceptance, and no installer was run.


### Windows manifest-lock test

The Windows-only acceptance test runs on `windows-latest` and proves the prepared manifest cannot be overwritten or deleted while `lock_prepared_manifest` holds its handles. It does not start WinGet or execute an installer. The first successful Windows run at commit `3b8fd1a45e30770614856f9e6aad97783d37590e` reported **14 passed**; the latest head is being rechecked.
