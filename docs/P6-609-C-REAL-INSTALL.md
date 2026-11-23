# P6-609-C — Real WinGet install path

## Goal

Move `software.install` from the legacy preview-only approval flow to a real,
Windows-local WinGet execution path. `software.remove` and unrelated preview
flows remain unchanged.

## Request path

1. The user describes the requested software in natural language. Gemini returns
   a schema-constrained proposal; its package/source/method hints are untrusted.
2. The frontend/backend independently discover the exact package ID and version
   from the WinGet catalog. The backend reads and validates the exact manifest.
3. On Windows, the proposal endpoint stages the exact manifest-declared installer
   temporarily, verifies its SHA-256, validates Authenticode, and checks that
   the signer identity matches the Publisher in the exact WinGet manifest.
4. For DBeaver Community, the backend additionally checks the official GitHub
   release metadata and official asset SHA-256. This is an extra control, not a
   user-managed certificate pin.
5. The backend creates a separate immutable `SoftwareInstallPlan`. It is not a
   `DryRunPlan` and does not authorize execution by itself.
6. The user reviews the exact package/version and evidence, then completes a
   one-use TOTP challenge bound to the plan and evidence digests.
7. Approval is atomically persisted as a durable queue reservation.
8. Immediately before the side-effect boundary, the worker consumes a one-use
   Product Owner release nonce bound to task P6-609-C, the exact package/version,
   and the approval digest. The authorization expires within 15 minutes.
9. The Windows-local worker validates the approved binding and executes the
   approved WinGet manifest through the contained process executor.
10. The worker verifies the exact package ID and version after execution.
11. Timeout, nonzero WinGet exit, lease loss, or ambiguous verification never
    becomes a false success and is never automatically retried.

## API surface

- `GET /api/software/install/readiness` — non-secret platform, publisher, and
  bounded real-install release authorization readiness.
- `POST /api/software/install/proposals` — backend discovery, staging,
  SHA-256/Authenticode/publisher verification, evidence registration, and
  immutable install proposal creation.
- `POST /api/plans/{plan_id}/software-approval` — create an exact-action TOTP
  challenge for the evidence bound to that proposal.
- `POST /api/plans/{plan_id}/software-approval/confirm` — consume TOTP and
  persist the queue reservation.
- `GET /api/software/install/jobs/{reservation_id}` — return an owner-scoped
  lifecycle summary without exposing the approved binding or worker lease.
- `GET /api/plans/{plan_id}/software-approval/reservation` — recover the
  owner-scoped committed reservation after a client timeout without creating or
  dispatching another job.

No `software.install` action receives a legacy `DryRunPlan` from
`POST /api/plans`. Single-package install requests are routed into the WinGet
catalog flow. Multi-package development-environment planning remains
non-executable and does not mint an install preview. The generic
`/api/plans/{plan_id}/step-up` and `/approve` routes reject stale
`software.install` plans; they remain for legacy preview use cases such as
software removal.

## Installer execution policy

- MSI/MSIX/AppX installers use WinGet silent mode.
- EXE installers are accepted only when the selected WinGet manifest declares a
  valid `InstallerSwitches.Silent` value. That value is copied into immutable
  approval evidence and the generated local manifest; Gemini and the frontend
  cannot provide or override it. EXE candidates without it are rejected.
- Exact installed-package verification treats WinGet `NO_APPLICATIONS_FOUND`
  as confirmed absence. Successful but unparseable inventory output remains
  ambiguous and cannot trigger an install or report success.

## Publisher trust

- Windows Authenticode chain validation is the platform trust decision.
- The backend requires the signer Organization (O), or Common Name (CN) only
  when O is absent, to match the Publisher in the independently fetched exact
  WinGet manifest after conservative formatting/legal-suffix normalization.
  A conflicting O is never bypassed by a CN match.
- The signer subject and certificate DER SHA-256 fingerprint are bound into
  immutable approval evidence. The fingerprint is evidence for substitution
  resistance and audit; it is not a per-package trust pin.
- No `AI_AGENT_DBEAVER_SIGNER_SHA256` setting, manual fingerprint copy, or
  trust-on-first-use step is required.
- DBeaver retains an additional SHA-256 cross-check against its official GitHub
  release metadata. The WinGet community manifest remains package metadata and
  must not be described as Microsoft endorsement of the software.
- If the signature chain, signer identity, manifest Publisher, or hash cannot
  be verified unambiguously, the proposal fails closed.

## Windows inspection-only command

After updating the branch and running `scripts/setup.ps1`, the following
command inspects the latest official DBeaver Community Windows x64 release:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\acceptance\P6-609-C\inspect_dbeaver_signer.ps1
```

It downloads the official release asset to a temporary directory, checks the
official SHA-256 digest and Authenticode signature, and prints the signer
subject and certificate fingerprint for diagnostics. It does **not** execute
or install DBeaver, does not configure an environment variable, and deletes
the temporary files.

The separate generic publisher acceptance command is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\acceptance\P6-609-C\verify_generic_publishers.ps1
```

It checks GitHub Desktop and Discord against their exact WinGet manifest
versions, downloads to temporary directories, validates SHA-256 and
Authenticode publisher identity, and deletes the files. It does **not** execute
either installer or install software. This check has passed on a GitHub-hosted
Windows runner; it is not a substitute for target-machine end-to-end testing.

## Current acceptance gates

- Generic publisher verification has passed on a GitHub-hosted Windows runner
  for GitHub Desktop and Discord. No installer was executed.
- The target Windows machine still needs end-to-end acceptance of DBeaver
  proposal creation, TOTP confirmation, durable queue insertion, contained
  WinGet execution, and exact post-install verification.
- The first live package is DBeaver Community. It must be reviewed and
  explicitly authorized at the package/version level before execution.
- No live installation is authorized by CI or by merging this PR. A local
  operator must explicitly run `scripts/authorize-real-install.ps1` for the
  exact package/version, then approve that exact artifact with TOTP.
- The Windows secure-storage adapter still requires its documented independent
  native security review before release; native integration CI alone does not
  satisfy that review gate.
- PR #170 and stacked PR #171 remain Draft and unmerged until review, the
  Windows storage gate, and target-Windows acceptance are complete.
