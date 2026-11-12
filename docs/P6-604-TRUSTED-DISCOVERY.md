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

The chat UI recognizes explicit install commands (Thai `ติดตั้ง ...` / `ช่วยติดตั้ง ...`, and English `install ...` / `please install ...`) and routes the product-name remainder directly to the authenticated discovery API. This path does not ask Gemini or another AI model to recommend or construct a Package ID. The backend searches the signed Microsoft catalog and returns candidate IDs and version hints directly from the catalog. The user must choose the exact candidate before the backend reads its manifest.

The chat UI asks the user to choose the exact Package ID and then an exact version. The catalog's latest-version field is displayed as a reference hint only and is never auto-selected. The manifest reader accepts an exact PackageIdentifier and optional exact version. If version is omitted, it returns the available version list and requires an explicit version choice; it never guesses that the lexicographically greatest version is the latest release. The current UI requests x64 user-scope manifest metadata; the backend rejects unsupported architecture/scope combinations.

The catalog index is cached in memory for one hour. Its MSIX is held only in a bounded temporary file for signature validation and is deleted after loading; the SQLite index is loaded into memory, so no persistent catalog database is written to the user's PC.

A catalog search result is only a package-name/ID candidate. The UI displays the exact publisher, version, architecture, user scope, installer type/domain, hashes, source commit, and source manifest link returned by the backend. A manifest result is always `CONDITIONAL`. It is not a `VerifiedPackageEvidence` and cannot be passed to the install adapter.

For the known DBeaver Community Package ID, a backend-owned trust anchor cross-checks the manifest against the latest release from the official `dbeaver/dbeaver` GitHub repository. It compares the exact release tag, Windows architecture asset URL, and GitHub-provided SHA-256 digest. A version, URL, or digest mismatch returns `SOURCE_MISMATCH`; inability to reach or validate the official release returns `SOURCE_CHECK_UNAVAILABLE`. Both states are blocked in the UI. Unknown publishers remain `NOT_CHECKED` and conditional; AI and frontend cannot add trust anchors.

The DBeaver check demonstrates why this matters: the WinGet manifest currently reports version `7.3.5`, while the official DBeaver release is `26.2.4` (checked 2026-11-12). The manifest is therefore blocked rather than treated as a safe current release.

A bounded staging service is implemented but is not wired to any API, approval route, or tool handler. It accepts only a backend `InstallerCandidate` whose official release version and SHA-256 match, downloads with HTTPS, no redirects, fixed timeouts, a 512 MiB ceiling, bounded streaming, and content-length checks, verifies both manifest and official release hashes, and then calls Windows WinVerifyTrust through the Authenticode verifier. Partial files are deleted on failure. The staged file is never executed. This service must only be called after exact-action approval is integrated; no staging download has been made on the user's PC.

## Required next stages

1. Expand the backend-owned publisher trust-anchor registry only with independently verified vendor-controlled sources.
2. Add a backend-only evidence registry that accepts results only from the completed release and installer verifier.
3. Bind the registry evidence to the existing exact-action approval challenge and approval digest.
4. Keep installation dispatch disabled until independent A4 review, negative tests, CI, local acceptance, and separate Product Owner enablement approval.

## Security invariants

- AI and frontend values are untrusted search hints only; neither can submit publisher, installer URL, hash, signature result, or evidence ID as verified facts.
- Unknown or inconsistent data fails closed.
- A changed package ID, version, architecture, scope, installer URL, or installer hash requires new discovery and new approval.
- No real installation is authorized by this task.
