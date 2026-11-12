# P6-604 — Trusted WinGet Manifest Discovery

## Status

Implementation in progress. This task is read-only discovery only. It does not invoke WinGet, download an installer, create approval evidence, or change the Windows host.

## Source and trust boundary

- Search product names in Microsoft's official WinGet catalog index, `source2.msix`, from `https://cdn.winget.microsoft.com/cache/source2.msix`.
- Verify the MSIX with Windows `WinVerifyTrust`, require the expected Microsoft package identity and Publisher, validate the package structure, then load its `Public/index.db` into a read-only in-memory SQLite connection.
- Search only the catalog's `packages` table using bound SQL parameters. The index provides candidate names, IDs, monikers and latest-version hints; it does not itself authorize installation.
- After the user selects a candidate, read its exact multi-file manifest from the Microsoft-owned `microsoft/winget-pkgs` repository through the fixed `api.github.com` HTTPS origin.
- Resolve one repository commit first, then pin all manifest reads to that immutable commit SHA.
- Treat catalog membership and manifest hashes as source/integrity evidence, not proof that the publisher endorses the package or that the installer is harmless.
- Do not follow HTTP redirects. Bound response size, timeout, file count, package ID syntax, archive size, and manifest parsing.
- Do not invoke `winget search`, `winget show`, `winget install`, or any other local package-manager command.
- Do not download installer URLs during discovery.

## Current implementation boundary

The backend first searches the signed Microsoft catalog by the user's product-name query. It returns candidate IDs and version hints directly from the catalog; AI is not used to recommend Package IDs. The user must choose a candidate before the backend reads its exact manifest.

The manifest reader accepts an exact PackageIdentifier and optional exact version. If version is omitted, it returns the available version list and requires an explicit version choice; it never guesses that the lexicographically greatest version is the latest release.

The catalog index is cached in memory for one hour. Its MSIX is held only in a bounded temporary file for signature validation and is deleted after loading; the SQLite index is loaded into memory, so no persistent catalog database is written to the user's PC.

A catalog search result is only a package-name/ID candidate. A manifest result is always `CONDITIONAL`. It is not a `VerifiedPackageEvidence` and cannot be passed to the install adapter. The manifest reader records the publisher and installer URL/hash, but it does not yet independently establish the publisher's official distribution channel or inspect the downloaded binary's Authenticode signer. Those gaps are explicit limitations.

## Required next stages

1. Cross-check product identity, edition, publisher, and installer domain against vendor-controlled official information.
2. Add a bounded staging downloader and file hash/Authenticode verification without executing the file.
3. Add a backend-only evidence registry that accepts results only from the completed verifier.
4. Bind the registry evidence to the existing exact-action approval challenge and approval digest.
5. Keep installation dispatch disabled until independent A4 review, negative tests, CI, local acceptance, and separate Product Owner enablement approval.

## Security invariants

- AI and frontend values are untrusted search hints only; neither can submit publisher, installer URL, hash, signature result, or evidence ID as verified facts.
- Unknown or inconsistent data fails closed.
- A changed package ID, version, architecture, scope, installer URL, or installer hash requires new discovery and new approval.
- No real installation is authorized by this task.
