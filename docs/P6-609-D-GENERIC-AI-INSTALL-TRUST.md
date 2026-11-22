# P6-609-D — Generic AI-driven install trust

## Product direction

Gemini is the planning layer: it interprets the user's request and proposes an exact package/version and installation approach. Gemini does not supply trusted installer bytes, signer identities, hashes, executable paths, or arbitrary commands. The backend independently resolves and verifies the exact WinGet package and remains the only execution authority.

DBeaver is the first acceptance package, not a hard-coded product boundary.

## Target workflow

1. Gemini proposes a package ID, exact version, architecture, and a human-readable rationale.
2. Backend independently resolves that exact package/version from Microsoft's WinGet catalog and pinned community manifest revision. AI-provided URLs, hashes, publisher claims, commands, and arguments are ignored.
3. Backend downloads only the manifest-declared installer URL over bounded HTTPS, verifies SHA-256 against the exact manifest, and validates the Windows Authenticode signature using Windows trust APIs.
4. Backend compares the Authenticode signer identity (certificate subject organization/common name) with the Publisher declared in the exact WinGet manifest. A mismatch, absent signer identity, invalid/revoked/untrusted chain, or unverifiable publisher fails closed.
5. Backend creates an immutable, exact-package install proposal. The user reviews package, version, publisher, scope, and evidence, then confirms with TOTP.
6. The durable queue and contained WinGet worker execute only the approved manifest. The worker verifies exact package ID/version after installation and never retries an ambiguous result automatically.

## Trust model

- Remove the DBeaver-only environment-variable certificate fingerprint as a prerequisite for the general install path. Do not replace it with automatic trust-on-first-use or a model-supplied fingerprint.
- Use Windows Authenticode chain validation as the platform trust decision, and require signer identity to match the Publisher in the independently fetched WinGet manifest.
- Keep package source, manifest schema, package ID/version, architecture, scope, installer URL, SHA-256, dependency policy, and redirect validation backend-enforced.
- A new package does not require the user to copy a certificate hash into PowerShell. If signer identity cannot be unambiguously matched, block the proposal and explain why.
- The WinGet community manifest is package metadata, not proof that Microsoft itself authored or guarantees the software. The UI must not describe it as Microsoft-vetted software. The backend must disclose this trust boundary.
- Do not execute Gemini-generated scripts or commands. WinGet remains the only enabled installer adapter in this slice.
- Keep exact-action TOTP, durable queue, process containment, no elevation, user scope, and post-install verification.

## Implementation work

1. Replace the DBeaver-specific release verifier/pin gate with a generic manifest + Authenticode identity verification policy.
2. Refactor installer staging/evidence so non-DBeaver packages can be verified without a vendor-specific GitHub release API, while preserving DBeaver's stronger official release SHA cross-check where available.
3. Ensure generic evidence binds the exact signer subject and certificate fingerprint into the immutable approval digest.
4. Remove the DBeaver-only readiness allowlist and expose generic capability/readiness plus explicit verification limitations.
5. Update frontend copy and proposal review to describe verified signer/publisher, source and limitations without claiming vendor endorsement.
6. Add positive and negative tests for multiple publishers/packages, subject mismatch, untrusted/invalid signatures, missing signer identity, hash mismatch, dependency manifests, and no AI-supplied execution data.
7. Keep the PR Draft and unmerged until CI and target-Windows acceptance pass.

## Acceptance boundary

CI may test verification logic with controlled fixtures. Windows acceptance must verify actual WinVerifyTrust behavior and at least two unrelated signed packages before enabling broad use. No live install is authorized by this document.