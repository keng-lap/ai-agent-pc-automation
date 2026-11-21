# P6-609-C — Real WinGet install path

## Goal

Move `software.install` from the legacy preview-only approval flow to a real,
Windows-local WinGet execution path. `software.remove` and unrelated preview
flows remain unchanged.

## Request path

1. The frontend searches Microsoft's signed WinGet source2 catalog.
2. The user selects an exact Package ID and version.
3. The backend re-reads the exact community manifest and checks it against the
   official DBeaver release metadata where a verifier is implemented.
4. On Windows, the proposal endpoint stages the exact installer temporarily,
   verifies the official release SHA-256, verifies Authenticode, and extracts
   the signer certificate SHA-256.
5. The backend evidence registry accepts the signer only when its certificate
   fingerprint matches a backend-owned trust pin. The staged file is removed
   after evidence registration.
6. A separate immutable `SoftwareInstallPlan` is created. It is not a
   `DryRunPlan` and it does not authorize execution by itself.
7. The user reviews the exact package and completes a one-use TOTP challenge
   bound to the plan digest and evidence digest.
8. Approval is atomically persisted as a durable queue reservation.
9. The Windows-local worker executes the approved WinGet manifest through the
   contained process executor, then verifies the exact Package ID and version.
10. Timeout, nonzero WinGet exit, lease loss, or ambiguous verification never
    becomes a false success and is never automatically retried.

## API surface

- `GET /api/software/install/readiness` — non-secret platform and publisher-pin
  readiness flags.
- `POST /api/software/install/proposals` — backend discovery, staging,
  Authenticode verification, evidence registration, and immutable install
  proposal creation.
- `POST /api/plans/{plan_id}/software-approval` — create exact-action TOTP
  challenge for the evidence ID bound to that proposal.
- `POST /api/plans/{plan_id}/software-approval/confirm` — consume TOTP and
  persist the queue reservation.

Explicit `software_install` requests do not receive a legacy `DryRunPlan`
from `POST /api/plans`; the frontend routes the interpreted target into the
WinGet catalog flow. The generic `/api/plans/{plan_id}/step-up` and
`/approve` routes also explicitly reject stale `software.install` plans.
They remain available only for legacy preview use cases such as software
removal. This prevents an install request from falling back to a mock Dry Run.

## DBeaver publisher pin

The evidence registry defaults to deny. It accepts only a 64-character
certificate DER SHA-256 fingerprint configured locally as:

```dotenv
AI_AGENT_DBEAVER_SIGNER_SHA256=<verified-certificate-sha256>
```

Do not copy a value from a third-party site, package manifest, or chat. Obtain
the pin from the Windows inspection script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/acceptance/P6-609-C/inspect_dbeaver_signer.ps1
```

The script downloads the latest official DBeaver Community Windows x64 release
asset, compares the file hash with the digest published in the official GitHub
release metadata, checks Windows Authenticode status, and prints the signer
certificate subject and DER SHA-256 fingerprint. It does **not** execute or
install DBeaver. Use `-ConfigureUserEnvironment` only after reviewing the
printed signer identity; the script asks before persisting the pin for the
current Windows user. PowerShell 5.1 can run the script; for the optional
persistence step use the same command with `-ConfigureUserEnvironment`. Restart the backend after configuring the pin.

## Current limitations / acceptance gates

- The trust pin is intentionally unset by default. Until the Windows signer
  inspection is reviewed and configured, the proposal endpoint returns a
  fail-closed response and no install can be queued.
- Windows-native inspection is still required to establish the actual DBeaver
  signer certificate fingerprint on the target Windows environment.
- After the pin is configured, run the proposal and TOTP workflow on Windows.
  A real DBeaver installation still requires the user's explicit package-level
  authorization; this PR does not install software during CI or merge.
- PR #170 remains Draft and unmerged until code review, CI, and Windows
  acceptance are complete.
