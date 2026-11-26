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

- `InstallerApprovalTicket` protocol v3 provides an HMAC-SHA256 integrity envelope bound to the canonical durable reservation UUID, plan ID, requester SID, Windows logon AuthenticationId (LUID), Terminal Services SessionId, approval digest, package ID/version/architecture, Machine Scope, installer SHA-256, nonce, and a maximum 120-second lifetime. The reservation UUID is included in the canonical MAC payload and mutation/replacement is rejected by Windows integration checks. `WindowsTokenIdentity` obtains SID, AuthenticationId, SessionId, and elevation from the current process primary token using Windows token APIs; the Helper must still independently resolve this reservation and compare every field against the durable Backend record before nonce consumption or execution.
- `DurableNonceStore` consumes a nonce using an atomic `FileMode.CreateNew` record named from SHA-256(nonce). A second thread, process, or newly constructed store instance cannot consume the same nonce again. Records are flushed to disk and are not overwritten.
- The nonce directory must be provisioned by an explicitly elevated setup action. `ProtectedApprovalKeyStore.ProvisionDirectory` sets a protected DACL and Administrators owner; runtime construction audits the owner and every allow ACE, rejects inherited permissions, and permits only SYSTEM and Administrators. `DurableNonceStore` reuses this audit, so nonce records and the DPAPI key share the same protected directory policy. Missing paths, reparse points, unexpected owners, inherited DACLs, or any allow ACE for another principal fail closed.
- The Helper must call ticket verification first, then atomically consume the nonce, and only then permit any privileged side effect. If consumption or durable storage fails, deny the action. Do not delete nonce records while their tickets could still be valid.
- `WindowsNamedPipePeerVerifier` derives the connected client PID from the pipe handle, opens that process's primary token, and checks SID, AuthenticationId LUID, Terminal Services SessionId, and the non-elevated requirement against the ticket. Its SDDL builder creates a protected requester-specific DACL (requester read/write; SYSTEM and Administrators full control). This is a verification/descriptor primitive only: the actual Helper pipe creation must use that descriptor and `PIPE_REJECT_REMOTE_CLIENTS`, and the client must independently verify the Helper server PID, elevated token, installed path, and pinned Authenticode signature.
- `DpapiApprovalKeyProtector` wraps/unwraps a 256-bit HMAC key with Windows DPAPI LocalMachine scope and application-specific optional entropy. It rejects undersized keys, malformed blob lengths, and tampered ciphertext; output buffers are released with the correct Windows `LocalFree` allocator.
- `ProtectedApprovalKeyStore` persists the DPAPI ciphertext as `approval-ticket-key.dpapi`. Elevated provisioning sets an explicit SYSTEM/Administrators-only protected DACL. Runtime audits directory and file owner/DACL, rejects reparse points and untrusted allow ACEs, and creates the ciphertext through a same-directory temporary file followed by an atomic no-overwrite rename. Concurrent initializers cannot observe a partially published key. DPAPI LocalMachine is not treated as an ACL.
- The key store and nonce store are implemented and covered by Windows CI. The Elevated Helper now loads the protected policy and existing key, validates the ticket envelope, and returns `DENIED_NOT_READY`; it does not yet resolve the durable Backend reservation, consume the nonce, or execute an installer. Key rotation/recovery policy and deployment-time invocation of elevated provisioning remain outstanding. These primitives alone do not authorize Machine Scope.

## Named-pipe transport implementation status

- `WindowsSecureNamedPipeServer` now creates the local pipe with the requester-specific protected DACL, `PIPE_REJECT_REMOTE_CLIENTS`, `FILE_FLAG_FIRST_PIPE_INSTANCE`, and overlapped I/O; it wraps the native handle for asynchronous managed stream operations.
- `WaitForApprovedClientAsync` waits with cancellation and validates the connected client PID's actual token SID, logon AuthenticationId (LUID), SessionId, and non-elevated status before the caller may process a frame.
- `InstallerHelperPipeProtocol` uses a four-byte big-endian length prefix, rejects empty or over-64-KiB frames before allocation, reads exact payload lengths, and rejects truncated/disconnected frames.
- Windows integration checks create and connect through the native server factory, inspect the actual peer token, reject mismatched SID/LUID/SessionId, and exercise valid, empty, oversized, and truncated frames. The positive test currently permits an elevated test runner; it does not prove a successful medium-integrity client handshake or a two-logon-session scenario.
- The server-side transport and peer-verification primitives are implemented. The separate Elevated Helper and unelevated Launcher now exist: the Launcher checks the protected policy and Helper signature before UAC, handles UAC cancellation without starting an installer, and verifies the Helper server identity before sending a bounded ticket. The Helper checks its elevated token, requester SID/logon/session, protected policy, client token, and ticket HMAC. Remaining gates are Backend reservation-to-Helper authorization, nonce consumption, staged-installer identity verification, wiring the Helper-owned Job Object runner to the verified installer, setup-time policy provisioning, and Windows 11 Home end-to-end installation. Machine Scope stays disabled.

## Elevated Helper and Launcher bootstrap status

- `src/windows/InstallerHelper` is a separate `net8.0-windows` executable. It rejects non-Windows execution, loads trust anchors from the fixed protected install policy, requires an actually elevated token whose SID matches the requester, checks that its own installed path and Authenticode certificate pin match that policy, creates the protected local Named Pipe, verifies the unelevated client token, and validates the ticket envelope. It still does not consume a nonce or launch an installer.
- `src/windows/InstallerLauncher` is a separate unelevated executable. It rejects an elevated caller, loads the fixed protected install policy, verifies the policy-pinned Helper Authenticode signature before UAC, binds the ticket to the current SID/AuthenticationId/SessionId, launches only through the `runas` ShellExecute verb, treats Win32 error 1223 as a terminal UAC cancellation, and verifies the connected server PID/token/path/signature before sending the bounded ticket frame. Its only accepted CLI option is `--ticket-file`; Helper path, certificate pin, and protected store path are no longer caller-supplied.
- `ProtectedInstallPolicy` now reads `install-policy.json` from the fixed `%ProgramFiles%\\AI Agent PC Automation\\Security` location. It rejects reparse points, unprotected/inherited DACLs, unexpected owners/principals, write access for BUILTIN\\Users, invalid certificate pins, Backend/Launcher/Helper paths outside the installed product directory, and approval-store paths outside the product ProgramData directory. Both Launcher and Helper reload the policy independently and verify their own installed binary identity/signature. The elevated `ProtectedInstallPolicy.Provision` setup primitive verifies the signed Backend, Launcher, and Helper binaries, provisions protected Program Files/ProgramData directories, creates the policy atomically without overwriting an existing policy, and provisions separate protected key/nonce stores. The policy now pins `AgentBackend.exe` at the fixed `%ProgramFiles%\\AI Agent PC Automation\\AgentBackend.exe` path and verifies its Authenticode identity and protected DACL alongside Launcher/Helper. `scripts/build-backend-windows.ps1` creates a PyInstaller Windows executable candidate, and `windows-packaged-backend.yml` builds and uploads it as an explicitly unsigned CI artifact. `scripts/sign-backend-windows.ps1` can sign a local build using a Code Signing certificate already present in the release operator's `CurrentUser\\My` store; it does not create/export a key or enroll trust. CI artifacts are not trusted install binaries; the exact release executable must be signed and then explicitly trusted before policy provisioning. The product installer/setup flow does not yet call this primitive; do not deploy until that integration and a certificate-rotation path are implemented.
- The current Backend approval API returns a durable queued reservation but does not yet mint a Windows Helper ticket or expose an independently verifiable reservation binding. The current C# ticket uses HMAC and the DPAPI key store is intentionally SYSTEM/Administrators-only; therefore the non-elevated Backend cannot legitimately sign a ticket with this key. The Helper now uses `LoadExisting` (never `LoadOrCreate`) and fails closed if setup has not provisioned the key. A dedicated Backend-to-Helper reservation-verification/signing channel is required; do not weaken the key ACL or accept an action digest supplied only by the untrusted Launcher.
- There is also an explicit contract mismatch to resolve before Machine Scope: the current Backend software-approval response is constrained to `scope: user`, while `InstallerApprovalTicket` accepts only `scope: machine`. Do not coerce one scope into the other or enable Machine Scope until the approval API, reservation payload, ticket protocol, and Helper policy agree on the exact requested scope.
- The Helper currently returns `DENIED_NOT_READY` after validating the ticket envelope and requester identity. It does not consume the durable nonce and does not launch an installer. This is intentional until the Helper can independently verify the durable Backend reservation and exact staged-installer identity. Machine Scope remains disabled.
- `WindowsJobObject.RunSuspendedCommandLine` creates the process suspended, assigns it to the Helper-owned Job Object before resume, waits for the root and descendants, and terminates the Job on timeout/cancellation. If assignment fails, it terminates the still-suspended process rather than resuming it. Integration checks cover clean exit and cancellation; the existing Job Object checks cover child-process containment and kill-on-close.
- CI builds the Security Core, Elevated Helper, and unelevated Launcher, then runs the Windows integration harness. A green build does not prove UAC interaction or Windows 11 Home installation; those require an interactive Windows test after the trust/policy and Backend bridge are complete.

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

The PR contains a non-elevated Backend, a separate unelevated Launcher, a separate Elevated Installer Helper, protected install-policy validation/provisioning primitives, a DPAPI LocalMachine-protected HMAC key store, a durable nonce-store primitive, an exact-action HMAC ticket (protocol v3, including a durable reservation UUID), and a Helper-owned Job Object process runner. The Launcher and Helper perform Windows token, SID, logon-session, Named Pipe peer, Authenticode, and protected-policy checks. The Helper deliberately stops at `DENIED_NOT_READY`: it does not yet independently resolve the reservation, consume the nonce, or start the staged installer. `ProtectedInstallPolicy.Provision` exists but is not yet wired into the signed product setup flow. The existing Backend User Scope executor is not a substitute for the future Elevated Helper execution boundary.

Keep Machine Scope disabled until the remaining authorization, nonce, staging, Helper execution, setup provisioning, and target Windows acceptance gates are complete. Passing Windows CI for the current primitives is not equivalent to a successful real install through the AI Agent application on Windows 11 Home.

## Trusted Backend-to-Helper authorization bridge (required before execution)

**Decision: preserve the existing approval flow.** The user-facing sequence remains proposal/evidence review, exact-action TOTP/step-up confirmation, atomic durable reservation, then execution dispatch. A Helper ticket is transport integrity metadata only; it is not a second approval and cannot create or broaden approval.

### Why the current bridge is intentionally not enabled

- The Backend currently runs as a non-elevated Python process and owns the approval database. A record read from that database is not independently trustworthy to an elevated Helper: the same interactive user can modify user-writable application state, and SQLite constraints/triggers are not cryptographic authenticity.
- The Helper's HMAC key and nonce store are intentionally writable only by SYSTEM/Administrators. Giving the HMAC key to the non-elevated Backend, putting it in a user-readable configuration file, or accepting a digest supplied by the Launcher would let a same-user process mint privileged tickets. Those are prohibited.
- The current approval evidence model explicitly supports `scope="user"`; the Helper ticket currently accepts only `scope="machine"`. Do not silently translate one scope into the other. The scope presented to the user, confirmed by TOTP, persisted in the reservation, and checked by the Helper must be identical.
- Consequently the Helper must continue to return `DENIED_NOT_READY`. It must not consume the nonce or create an installer process until the bridge below is implemented and independently tested.

### Required bridge design

1. Keep the existing TOTP challenge and confirmation endpoints as the sole user approval step. Confirmation must continue to atomically consume the one-use challenge and create the immutable reservation; no new confirmation prompt is introduced.
2. Package the Backend as a signed, fixed-path executable installed under the administrator-protected Program Files product directory. A Windows PyInstaller build candidate and CI artifact workflow now exist; they intentionally produce unsigned artifacts, which cannot be provisioned as trusted runtime binaries. The installed Backend executable and its runtime dependencies must be protected against standard-user modification. Running the Python development server from a user-writable checkout is not an eligible production authorization authority.
3. The protected install policy now includes the exact Backend executable path and pinned Authenticode certificate identity (the same locally enrolled, self-signed code-signing identity is acceptable). Provision and validate its DACL, owner, reparse-point status, and signature exactly as for Launcher/Helper.
4. Add a dedicated local-only Backend reservation IPC endpoint. The Helper connects to that endpoint and independently verifies the server PID, token SID, logon AuthenticationId, session ID, fixed executable path, protected file ACL, and pinned Authenticode signature. The endpoint must reject remote clients and use bounded, versioned framing.
5. The Helper requests the reservation by canonical UUID and a fresh per-request challenge. The Backend returns a read-only snapshot sourced from the durable reservation and immutable approval binding. The response must include reservation/approval/plan IDs, owner/session binding, reservation state, plan and action digests, package ID/version/architecture/scope, installer SHA-256, publisher/signature evidence, source/manifest identity, and the exact approved silent-install policy. No free-form executable path or command line is accepted.
6. The Helper validates the snapshot against every corresponding ticket field and its own fresh challenge. It rejects missing, extra, stale, revoked, expired, mismatched, or non-queued reservations. The Backend IPC response is accepted only from the protected signed Backend process described above; a JSON snapshot alone is not proof.
7. Only after all checks pass may the Helper atomically consume the protected nonce, re-hash and re-verify the staged installer, create it suspended, assign it to the Helper-owned Job Object, and resume it. Any failure before process creation is a denial. Any ambiguous result after process creation becomes UNKNOWN and is never automatically retried.

### Acceptance gates for this bridge

- Negative tests: forged or modified database rows, fake Backend process, wrong PID/path/signature/certificate pin, wrong SID/LUID/session, remote pipe client, stale/revoked reservation, mismatched scope/digest/package/version/architecture/installer hash/publisher, changed installer bytes, replayed nonce, expired challenge, malformed/oversized/truncated IPC frames, and UAC cancellation.
- Positive tests: same approved proposal flows through the existing TOTP UI once, durable reservation is retrieved by the verified installed Backend, Helper validates exact fields, nonce is consumed exactly once, and the exact staged installer is contained by the Job Object.
- Windows 11 Home acceptance must run through the actual AI Agent PC Automation application and install the selected DBeaver Community package. CI-only checks do not satisfy this gate.
- Until all gates pass, keep Machine Scope disabled and keep Helper execution fail-closed. Do not merge this PR without explicit user approval.

