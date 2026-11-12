# P6-604 — Trusted WinGet Manifest Discovery

## Status

Implementation in progress. This task is read-only discovery only. It does not invoke WinGet, download an installer, create approval evidence, or change the Windows host.

## Source and trust boundary

- Read manifest data only from the Microsoft-owned `microsoft/winget-pkgs` GitHub repository through the fixed `api.github.com` HTTPS origin.
- Resolve one repository commit first, then pin all manifest reads to that immutable commit SHA.
- Treat repository membership and a valid manifest SHA-256 as source/integrity evidence, not proof that the publisher endorses the package or that the installer is harmless.
- Do not follow HTTP redirects. Bound response size, timeout, file count, package ID syntax, and manifest parsing.
- Do not invoke `winget search`, `winget show`, `winget install`, or any other local package-manager command.
- Do not download installer URLs during discovery.

## Current implementation boundary

The initial repository reader accepts an exact PackageIdentifier and optional exact version. If version is omitted, it returns the available version list and requires an explicit version choice; it never guesses that the lexicographically greatest version is the latest release.

A returned candidate is always `CONDITIONAL`. It is not a `VerifiedPackageEvidence` and cannot be passed to the install adapter. The current reader records the publisher and installer URL/hash from the manifest, but it does not yet independently establish the publisher's official distribution channel or inspect the downloaded binary's Authenticode signer. Those gaps are explicit limitations.

## Required next stages

1. Add a first-party catalog search path so the backend can search by the user's product name without treating AI output as a trusted package recommendation.
2. Cross-check product identity, edition, publisher, and installer domain against vendor-controlled official information.
3. Add a bounded staging downloader and file hash/AuthentiCode verification without executing the file.
4. Add a backend-only evidence registry that accepts results only from the completed verifier.
5. Bind the registry evidence to the existing exact-action approval challenge and approval digest.
6. Keep installation dispatch disabled until independent A4 review, negative tests, CI, local acceptance, and separate Product Owner enablement approval.

## Security invariants

- AI and frontend values are untrusted search hints only; neither can submit publisher, installer URL, hash, signature result, or evidence ID as verified facts.
- Unknown or inconsistent data fails closed.
- A changed package ID, version, architecture, scope, installer URL, or installer hash requires new discovery and new approval.
- No real installation is authorized by this task.
