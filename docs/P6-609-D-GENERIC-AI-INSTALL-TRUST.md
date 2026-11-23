# P6-609-D — Generic AI-driven install trust

## Product direction

Gemini is the planning layer: it interprets the user's request and proposes an exact package/version and installation approach. Gemini does not supply trusted installer bytes, signer identities, hashes, executable paths, or arbitrary commands. The backend independently resolves and verifies the exact WinGet package and remains the only execution authority.

DBeaver is the first acceptance package, not a hard-coded product boundary.

## Target workflow

1. Gemini proposes a package ID, exact version, architecture, and a human-readable rationale.
2. Backend independently resolves that exact package/version from Microsoft's WinGet catalog and pinned community manifest revision. AI-provided URLs, hashes, publisher claims, commands, and arguments are ignored.
3. Backend downloads only the manifest-declared installer URL over bounded HTTPS, verifies SHA-256 against the exact manifest, and validates the Windows Authenticode signature using Windows trust APIs.
4. Windows validates the Authenticode chain and extracts the signer certificate subject and DER SHA-256 fingerprint. Backend requires an exact normalized match between the certificate Organization (O) and the Publisher in the exact WinGet manifest; Common Name (CN) is considered only when Organization is absent. A mismatch, ambiguous identity, absent signer identity, invalid/revoked/untrusted chain, or unverifiable publisher fails closed.
5. Backend creates an immutable, exact-package install proposal. The user reviews package, version, publisher, scope, and evidence, then confirms with TOTP.
6. The durable queue and contained WinGet worker execute only the approved manifest. The worker verifies exact package ID/version after installation and never retries an ambiguous result automatically.

## Trust model

- No per-package certificate fingerprint pin or user-managed environment variable is required. The Windows Authenticode chain is the platform trust anchor; the backend binds the verified certificate DER SHA-256 fingerprint to the immutable approval digest for audit and substitution resistance. This is not trust-on-first-use.
- Use Windows Authenticode chain validation as the platform trust decision, and require the signer Organization (O), or CN only if O is absent, to exactly match the Publisher in the independently fetched WinGet manifest after conservative formatting/legal-suffix normalization. Never accept a CN match when a conflicting O is present.
- Keep package source, manifest schema, package ID/version, architecture, scope, installer URL, SHA-256, dependency policy, and redirect validation backend-enforced.
- A new package does not require the user to copy a certificate hash into PowerShell. If signer identity cannot be unambiguously matched, block the proposal and explain why.
- The WinGet community manifest is package metadata, not proof that Microsoft itself authored or guarantees the software. The UI must not describe it as Microsoft-vetted software. The backend must disclose this trust boundary.
- Do not execute Gemini-generated scripts or commands. WinGet remains the only enabled installer adapter in this slice.
- Keep exact-action TOTP, durable queue, process containment, no elevation, user scope, and post-install verification.

## Implementation work

1. Implement generic manifest + Authenticode identity verification for packages without vendor release APIs; retain DBeaver's stronger official release SHA-256 cross-check as an additional control.
2. Refactor installer staging/evidence so non-DBeaver packages use the exact manifest URL and SHA-256, while preserving DBeaver's stronger official release SHA cross-check.
3. Ensure generic evidence binds the exact signer subject and certificate fingerprint into the immutable approval digest.
4. Remove the DBeaver-only readiness allowlist and expose generic capability/readiness plus explicit verification limitations.
5. Update frontend copy and proposal review to describe verified signer/publisher, source and limitations without claiming vendor endorsement.
6. Add positive and negative tests for multiple publishers/packages, subject mismatch, untrusted/invalid signatures, missing signer identity, hash mismatch, dependency manifests, and no AI-supplied execution data.
7. Keep the PR Draft and unmerged until CI and target-Windows acceptance pass.

## Current implementation status

- The DBeaver-only certificate fingerprint environment-variable gate has been removed from the evidence registry.
- Generic packages may be staged from the exact WinGet manifest URL and SHA-256 without a vendor release API.
- Evidence minting requires a successful Windows Authenticode verification, a non-empty signer subject, a 64-character certificate DER SHA-256 fingerprint, and an exact manifest Publisher match. The fingerprint and subject are included in the immutable approval evidence.
- DBeaver continues to require its official release metadata and official asset SHA-256 cross-check.
- These code paths still require CI and target-Windows acceptance; implementation does not mean live installation is enabled.

## Acceptance boundary

CI may test verification logic with controlled fixtures. Windows acceptance must verify actual WinVerifyTrust behavior and at least two unrelated signed packages before enabling broad use. No live install is authorized by this document.