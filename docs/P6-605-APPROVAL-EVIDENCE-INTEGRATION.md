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
  official release URL, successful Authenticode validation, signer subject,
  and a 64-character SHA-256 fingerprint of the signer's certificate DER.

The frontend and HTTP request schema accept only an opaque evidence ID. They
cannot submit or override package ID, publisher, version, URL, hashes,
architecture, scope, signer subject, certificate fingerprint, timestamps, or
approval digest. The approval challenge response displays the package identity,
publisher, exact version, installer URL and hashes, signer subject, certificate
fingerprint, and evidence expiry so the user can inspect the proposal before
entering TOTP.

Evidence is immutable, process-local, bounded to 128 records, and expires no
later than 15 minutes after verification. A binding hashes the complete
evidence snapshot, including the signer certificate fingerprint, and the
server-owned plan digest. Approval re-resolves the evidence, revalidates
freshness, and compares the digest before consuming TOTP. A successful TOTP
confirmation consumes the plan binding as well; repeated confirmation or a
new challenge for that consumed binding is rejected until the evidence expires.

## Signer certificate identity — implemented, Windows validation pending

`WindowsMsixSignatureVerifier` retains the WinVerifyTrust state long enough to
retrieve the primary signer certificate through the documented WinTrust
provider helper functions. It extracts both the X.500 subject and SHA-256 of
the exact certificate DER. `WindowsAuthenticodeVerifier` passes both values
into `StagedInstaller` only when trust validation and identity extraction
succeed. The catalog loader also exposes the verified Microsoft source package
signer's subject and certificate fingerprint for Windows acceptance testing.

The helper functions are documented by Microsoft but Microsoft notes that they
may change or become unavailable. The implementation therefore treats every
missing export, malformed provider state, invalid certificate context, or
fingerprint extraction error as a hard failure. A Windows CI test checks the
Microsoft source2 MSIX signer identity; this does not yet validate a third-party
installer signer. <https://learn.microsoft.com/en-us/windows/win32/api/wintrust/nf-wintrust-wthelpergetprovcertfromchain>

The certificate fingerprint is included in immutable evidence and therefore
in the approval digest. The registry's trust callback now receives this
fingerprint, not the subject string. No publisher trust anchors are configured;
the registry still rejects all evidence by default until an independently
verified, backend-owned certificate fingerprint is configured.
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