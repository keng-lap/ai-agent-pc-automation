# P6-605 — Approval Evidence Integration

## Scope

P6-605 adds a backend-only, process-local evidence registry and a separate
software-approval API. It binds one exact `software.install` plan to one
verified package evidence record, then binds the resulting approval digest to
the existing owner/session-bound, one-use TOTP challenge.

The approval API returns `APPROVED_NOT_EXECUTED`. It does not call WinGet,
the installer stager, the adapter, a background worker, or any machine-changing
handler. Existing Dry Run behavior is unchanged.

## Evidence provenance

The registry accepts only backend model instances:
- `InstallerCandidate` with official publisher release verification marked
  `VERIFIED` and exact official version/hash/release URL;
- `StagedInstaller` with matching package ID, version, architecture, hash,
  official release URL, successful Authenticode validation, and a non-empty
  signer subject.

The frontend and HTTP request schema accept only an opaque evidence ID. They
cannot submit or override package ID, publisher, version, URL, hashes,
architecture, scope, signer subject, timestamps, or approval digest. The
approval challenge response displays the package identity, publisher, exact
version, installer URL and hashes, signer subject, and evidence expiry so the
user can inspect the proposal before entering TOTP.

Evidence is immutable, process-local, bounded to 128 records, and expires no
later than 15 minutes after verification. A binding hashes the complete
evidence snapshot and the server-owned plan digest. Approval re-resolves the
evidence, revalidates freshness, and compares the digest before consuming TOTP.

## Signer identity extraction — implemented, Windows validation pending

`WindowsMsixSignatureVerifier` now retains the WinVerifyTrust state long enough
to retrieve the primary signer certificate through the documented WinTrust
provider helper functions, then reads its X.500 subject with `CertGetNameStringW`.
`WindowsAuthenticodeVerifier` passes that subject into `StagedInstaller` only
when trust validation and subject extraction both succeed. Missing or malformed
subject data causes staging to fail closed.

The helper functions are documented by Microsoft but Microsoft notes that they
may change or become unavailable. The implementation therefore treats every
missing export, malformed provider state, or certificate extraction error as a
hard failure. A Windows CI test checks extraction against a Windows-signed
PowerShell binary; that test must pass before this capability is considered
validated. <https://learn.microsoft.com/en-us/windows/win32/api/wintrust/nf-wintrust-wthelperprovdatafromstatedata>

No publisher trust anchors are configured. Extracting a signer subject proves
which certificate signed the file; it does not establish that the signer is the
expected publisher. The evidence registry still rejects all evidence by default
until an independently verified, backend-owned publisher anchor is configured.
Do not populate the anchor from the manifest publisher string, URL, AI output,
or frontend data. The current DBeaver WinGet manifest also remains blocked
because its version does not match the official release.

## API

- `POST /api/plans/{plan_id}/software-approval` accepts only `evidence_id`.
  It creates a challenge bound to the approval digest.
- `POST /api/plans/{plan_id}/software-approval/confirm` accepts only
  `challenge_id` and a six-digit TOTP code. It consumes the exact challenge
  and returns an approval receipt with `APPROVED_NOT_EXECUTED`.

Both routes require the existing authenticated session dependency. The binding
store also records owner and session IDs and rejects cross-session use.

## Explicit exclusions

- No WinGet invocation or installer execution.
- No background job creation or dispatch.
- No adapter changes.
- No persistence of evidence or approval bindings across process restarts.
- No enablement or authorization to make changes to the user's Windows PC.

## Required next gates

1. Implement and independently review Windows Authenticode signer-subject extraction.
2. Add publisher-specific signer trust anchors and negative tests for wrong signer,
   unsigned binaries, expired certificates, and unavailable revocation data.
3. Wire only trusted stager output into the evidence registry; never expose a
   registration endpoint that accepts evidence fields.
4. Add API tests proving evidence substitution, cross-session use, stale evidence,
   replayed TOTP, and digest changes are rejected.
5. Run CI and independent A4 review before any runtime integration is considered.