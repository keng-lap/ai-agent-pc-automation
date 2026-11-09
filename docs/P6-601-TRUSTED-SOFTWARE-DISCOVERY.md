# P6-601 — Trusted Software Discovery Baseline

## Status and authority

**Planning requirement recorded under P6-601.** This document does not authorize a package-manager integration, software download, installer execution, or any real Windows machine change.

## Product decision recorded

- WinGet is the primary package source for Windows applications.
- Chocolatey is a secondary Windows package source, not an automatic trust guarantee.
- npm is for Node.js packages and developer tools, not a generic Windows desktop-app source.
- The official publisher website/documentation is the vendor-of-record used to verify product identity, release, and supported distribution channels.

## Discovery policy

The agent must act as a software-source researcher before proposing installation. It must identify exact product/edition, publisher, package ID, version, architecture, package source, installer origin, integrity evidence, and relevant risks. It must present evidence and uncertainty to the user. It must not download or execute anything during discovery.

### Source ordering

1. Official publisher site establishes product identity and official distribution channels.
2. WinGet is searched first for Windows applications.
3. Microsoft Store or a publisher-operated repository may be used when the publisher identifies it as an official channel.
4. Chocolatey is considered only if no suitable verified WinGet candidate exists or the publisher explicitly recommends it.
5. npm is considered only for a requested Node.js package/tool.

### Minimum evidence per candidate

| Evidence | Required check |
|---|---|
| Product identity | Exact name and edition; no Community/Enterprise substitution |
| Publisher | Manifest/package publisher agrees with official publisher evidence |
| Package identity | Exact PackageIdentifier / package name and registry/source |
| Version | Exact version and comparison with current stable publisher release |
| Installer origin | HTTPS URL and domain reachable from publisher's official site; disclose redirects |
| Integrity | Manifest/package integrity digest (e.g. WinGet InstallerSha256 or npm integrity) |
| Signature | Authenticode signer and certificate status when installer format supports it |
| Architecture/scope | x64/ARM64 and user/machine scope are explicit |
| Package behavior | Installer type, dependencies, scripts, privilege needs, network destinations |
| Freshness | Current manifest/release state and checked-at timestamp |

### Source-specific checks

**WinGet**
- Query exact source and package ID; do not rely on third-party catalog aggregators.
- Inspect the current manifest, not only search-result display text.
- Check Publisher, PackageIdentifier, PackageVersion, InstallerUrl, InstallerSha256, InstallerType, architecture, scope, and applicable signature metadata.
- Confirm the installer domain is an official publisher source. A passing repository validation or hash check is useful evidence but is not a malware-free guarantee.

**Chocolatey**
- Inspect package contents, nuspec, PowerShell install/uninstall scripts, URLs, checksum handling, package version, moderation/verification state, and publisher linkage.
- Treat package scripts as executable code. Moderation is a signal, not a guarantee about the underlying binary.
- Prefer a publisher-maintained package or official vendor download over an unrelated community maintainer when both are available.

**npm**
- Use only for Node.js packages and developer tools.
- Check exact package/scope, npm metadata, repository/homepage ownership, maintainers, version, integrity digest, provenance/attestation where available, dependency tree, and lifecycle scripts.
- Treat lifecycle scripts as code execution. Disclose relevant scripts and dependencies; do not silently assume package installation is inert.

## Trust outcomes

- **VERIFIED CANDIDATE:** required identity, origin, version, and integrity evidence is consistent; may be shown for separate approval.
- **CONDITIONAL:** a material evidence gap remains; disclose it and wait for a Product Owner decision.
- **BLOCKED:** mismatch, suspicious origin, integrity/signature failure, or unknown publisher; do not propose installation.
- **NOT FOUND:** no suitable package in approved sources; report honestly, do not invent a package ID or URL.

## Example — DBeaver Community

For "install DBeaver", the agent first checks the official DBeaver download/documentation site to distinguish Community from Enterprise and identify the current stable release. It then searches WinGet and inspects the current manifest for the exact package ID. DBeaver.DBeaver.Community is a known candidate identifier, not a permanent allowlist entry; its current presence, version, publisher, installer URL, hash, and signature must be rechecked at request time. The official DBeaver site documents Windows downloads and a Chocolatey install channel; this does not itself prove that any particular Chocolatey package or WinGet manifest is safe or current.

The report must show source links, exact package ID, exact version, publisher match, installer domain, hash/signature evidence, architecture, freshness, and caveats. If the package manager is behind the publisher's current release, report the mismatch and do not silently switch to a direct download.

## Future implementation boundary

A future install adapter must accept a strict typed request with a fixed source enum and exact package ID/version/architecture/scope. It must not accept arbitrary command text, URLs, executable paths, shell arguments, scripts, or model-supplied handler names. The discovery evidence and immutable install proposal must be bound to the exact approval digest; any material change requires a new review and approval.

This document is planning only. Real package-manager invocation remains disabled pending a separate bounded runtime task, F-516-01 A4 prerequisite, independent A4 review, negative tests, CI evidence, and explicit Product Owner approval to enable the specific capability.