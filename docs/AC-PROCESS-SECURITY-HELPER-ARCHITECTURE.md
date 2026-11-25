# AC & Process Security — Elevated Installer Helper Architecture

Status: **Architecture specified; Helper implementation and Windows acceptance tests remain blocked.**
Scope: PR #172 only. This document does not authorize Machine Scope or change the current User Scope installer.

## Security invariants

1. FastAPI Backend and every in-process Agent/worker remain non-elevated for their entire lifetime.
2. The Backend never changes its token, requests UAC for itself, or runs an installer elevated.
3. Only a separately built, signed Elevated Installer Helper may receive an elevated token.
4. No installation starts before the Helper validates the immutable approval ticket, caller identity, exact package action, and its own trusted signature.
5. Any uncertainty in signature, token, SID, ticket, IPC, or process containment fails closed. No automatic retry is permitted after an ambiguous execution result.
6. Machine Scope remains unavailable until the Helper is implemented, signed, independently verified, and passes the target Windows acceptance matrix.

## Process topology

```text
Browser
  |
  v
FastAPI Backend + in-process Agent (medium/non-elevated token only)
  |  authenticated approval + one-time ticket
  v
Fixed, signed, unelevated UAC Launcher (no installer authority)
  |  requests elevation for one fixed Helper binary only
  v
Elevated Installer Helper (high token; narrow protocol)
  |  owns its own Job Object; creates installer suspended
  v
WinGet / approved installer process tree
```

The Launcher is a minimal, separately signed bootstrap component. It accepts no executable path, command line, package identity, or arbitrary arguments from the browser. It may request UAC only for the fixed Helper binary at a verified installation path. It has no installer execution API and remains non-elevated. The Backend does not call `ShellExecute(runas)` and is never elevated.

## Backend / Agent runtime guard

- At ASGI server startup, query the current process effective access token using `OpenProcessToken(TOKEN_QUERY)` and `GetTokenInformation(TokenElevation)`.
- If the token is elevated, abort Backend startup before it serves requests or starts the install worker.
- If token inspection fails or returns an incomplete result, abort startup (fail closed).
- The in-process Agent and worker share the Backend process token; they cannot request or inherit a separate elevation path.
- This guard is not a substitute for Windows ACLs, code signing, or Helper-side token validation.
- A future out-of-process Agent must independently enforce the same non-elevated invariant.

## UAC and identity protocol

1. Backend atomically consumes/creates a short-lived, one-time ticket bound to:
   - original Windows user SID and logon session identity;
   - authenticated application session and approval/reservation ID;
   - immutable approval/action digest;
   - exact package ID, version, architecture, scope, publisher evidence, installer URL and SHA-256;
   - nonce, issue time, expiry (target 60–120 seconds), and protocol version.
2. Ticket is integrity-protected (MAC/signature using a narrowly scoped per-install secret) and stored/consumed durably with a unique nonce. It contains no OAuth, Gemini, TOTP, DPAPI master, or other reusable application secret.
3. Unelevated Launcher accepts only a fixed Helper path and opaque ticket handle. It verifies the fixed binary's Authenticode signature and pinned publisher policy before requesting UAC.
4. If UAC is cancelled, the Helper never starts; Backend records a safe cancellation result and verifies that no installer process was created. No retry is automatic.
5. Helper re-verifies its own Authenticode signature and expected publisher identity after launch. Signature invalid, untrusted chain, revoked certificate, wrong file hash, or verification API error => stop.
6. Helper obtains its own effective token using Windows token APIs. It verifies that it is elevated and obtains the effective user SID from the token. It compares that SID to the ticket's original user SID. Alternate credentials, SYSTEM, another administrator SID, or any mismatch => reject.
7. Helper validates ticket MAC, expiry, nonce, one-time state, session binding, approval digest, and all immutable package fields. It does not accept caller-supplied executable paths or free-form installer arguments.
8. Backend and Helper communicate over a local named pipe with a restrictive DACL for the expected logon SID. Both ends verify peer PID and token SID; message framing and maximum lengths are fixed. Disconnect or malformed message => UNKNOWN/stop, never assume success.

## Durable approval nonce primitive (implemented; not yet wired to Helper)

- `InstallerApprovalTicket` provides an HMAC-SHA256 integrity envelope bound to the requester SID, approval digest, package ID/version/architecture, Machine Scope, installer SHA-256, nonce, and a maximum 120-second lifetime.
- `DurableNonceStore` consumes a nonce using an atomic `FileMode.CreateNew` record named from SHA-256(nonce). A second thread, process, or newly constructed store instance cannot consume the same nonce again. Records are flushed to disk and are not overwritten.
- The nonce directory must be provisioned before runtime in an administrator-protected location. Its DACL must grant write access only to SYSTEM and Administrators; the runtime constructor rejects a missing directory and a reparse-point directory. The current primitive does not itself provision or audit the DACL.
- The Helper must call ticket verification first, then atomically consume the nonce, and only then permit any privileged side effect. If consumption or durable storage fails, deny the action. Do not delete nonce records while their tickets could still be valid.
- The HMAC key is not yet provisioned or protected by DPAPI, and the ticket/nonce path is not yet connected to Backend reservations or a running Helper. These primitives alone do not authorize Machine Scope.

## Local-first Helper signing and trust policy

The current product target is a locally installed Windows agent, not public software distribution. A paid public-CA Code Signing Certificate is **not a prerequisite**.

- Use a project-controlled self-signed Code Signing certificate for the locally installed Launcher and Helper. Keep the private key out of the application install directory and out of the runtime account; restrict signing to the release/build operator.
- During an explicit first-time machine setup, an administrator must enroll the certificate into the Windows trust stores required by Authenticode (Trusted Root Certification Authorities and Trusted Publishers). Explain the publisher identity and consequences before enrollment; do not silently add trust.
- Pin the expected certificate identity (SHA-256 certificate thumbprint/public-key identity) in the Launcher/verification policy as an additional publisher constraint. A valid signature from an unrelated certificate is not sufficient.
- Verify Authenticode trust with `WinVerifyTrust` and enforce the pinned project certificate identity. Verify the exact installed Helper immediately before UAC and again inside the Helper.
- Install Launcher/Helper under an administrator-protected directory; ordinary users and the unelevated Backend must not be able to replace binaries or alter the trust policy.
- If the certificate is missing, untrusted, expired, revoked, replaced, or cannot be verified; if the file changes; or if trust-store enrollment is incomplete, block Machine Scope. Do not fall back to unsigned execution.
- Define certificate renewal/rotation and recovery before production rollout. The self-signed certificate is a local trust mechanism, not a way to obtain public Windows reputation or eliminate SmartScreen warnings.
- CI may build unsigned artifacts for tests, but unsigned artifacts must never be eligible for Machine Scope.

## Installer Process Tree containment

- The Helper creates and owns a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; it does not borrow the Backend's Job Object.
- Create the fixed installer entry process with `CREATE_SUSPENDED`. Assign its process handle to the Helper-owned Job Object before calling `ResumeThread`.
- If Job Object creation, assignment, or resume fails, terminate the still-suspended process and stop. Never resume an uncontained process.
- Do not enable breakaway/silent-breakaway. Descendants must remain in the Job Object; verify active-process accounting until the entire tree exits.
- On cancellation, timeout, Helper shutdown, lease loss, or IPC failure, terminate the Job Object and wait for zero active processes. If termination/empty-state verification fails, mark outcome UNKNOWN and block subsequent attempts pending independent reconciliation.
- A Job Object constrains process membership, not every possible external service/deferred task. The supported installer contract must be explicit; installers that delegate work outside the contained tree are unsupported for this execution path.

## State machine and failure semantics

| Event | Required outcome |
|---|---|
| UAC cancelled | CANCELLED; no Helper/installer process |
| Wrong SID / non-elevated Helper token | DENIED; no installer process |
| Signature or ticket validation failure | DENIED; no installer process |
| Job Object assignment failure | FAILED; suspended process terminated, never resumed |
| User cancellation after resume | UNKNOWN until installed state is independently reconciled |
| Helper crash / IPC loss | UNKNOWN; never auto-retry |
| Job Object cannot prove tree termination | UNKNOWN; block further install attempts |
| Exact package/version independently verified | SUCCEEDED |

## Required Windows acceptance tests

Run on supported Windows 11 editions, including the nominated Windows 11 Home target:

- Backend launched with a genuinely elevated token refuses startup; medium-integrity/non-elevated launch succeeds.
- Token query API failure refuses startup.
- Launcher and Helper signature valid/invalid, wrong publisher, revoked/untrusted certificate, and binary replacement cases.
- UAC accept, UAC cancel, and alternate administrator credentials; verify actual effective SID and token, not UI assumptions.
- Wrong SID, wrong session, expired/replayed ticket, action digest mismatch, package/version/architecture/scope mutation, and concurrent ticket consumption.
- Helper Job Object contains WinGet and installer descendants; force termination, timeout, Helper crash, and IPC disconnect.
- Prove no installer process starts on UAC cancel or any pre-launch validation failure.
- Confirm Backend/Agent remain non-elevated throughout every scenario.

## Current implementation boundary

The PR currently contains a Backend-side User Scope WinGet executor, a Backend-owned Job Object, an exact-action HMAC approval-ticket primitive, and an atomic durable nonce-consumption primitive. The nonce directory ACL is a deployment prerequisite and is not yet provisioned/audited by code. The ticket and nonce primitives are not yet wired to DPAPI key protection, Backend reservations, a Launcher, or an Elevated Helper. The PR does **not** contain the Launcher, Elevated Helper, Helper-owned Job Object integration, SID/token handshake, or UAC protocol. The existing Backend Job Object does not satisfy the future Helper containment requirement.

Until those components and Windows tests exist, keep Machine Scope disabled. Do not describe the six AC items as passed merely because the architecture and Backend runtime guard exist.
