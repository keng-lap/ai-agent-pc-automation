# Machine Scope and UAC Security Design

Status: design and repository audit only. This document does not enable Machine Scope execution.

Target branch: `feat/runtime-diagnostics` (PR #172)
Audited HEAD: `b529455bc80abac2fac0bd405e83cfba0aa5d87f`

## 1. Non-negotiable security invariants

1. FastAPI, its worker thread, Browser, and Agent processes must remain unelevated for the entire operation.
2. Only a separately signed, narrowly scoped installer helper may receive a UAC-elevated token.
3. The helper may execute only one immutable, exact-action approval. It is not a shell, generic process launcher, or command broker.
4. A Machine Scope operation is unavailable unless helper identity, same-user identity, one-time authorization, IPC, and process-tree containment are all verified.
5. UAC cancellation, alternate-user credentials, expired/replayed authorization, signature failure, IPC failure, or containment failure must stop the operation. No fallback to an elevated backend or an uncontained process is permitted.
6. Plan Review and Dry Run remain the default. Discovery or scope selection never authorizes execution.
7. Preserve the existing `http://127.0.0.1:4200` frontend origin, Google OAuth, TOTP, and current-user DPAPI storage behavior.

## 2. Repository facts verified at the audited HEAD

### Current execution model

- `software_install_worker.py` runs as a worker in the FastAPI process. It claims a durable SQLite reservation, validates the immutable approval binding, and calls the WinGet executor.
- `winget_execution.py` uses the current user's packaged WinGet alias and starts WinGet with `CreateProcessW`, `CREATE_SUSPENDED`, then assigns the process to a Windows Job Object before resuming it.
- `process_containment.py` owns the Job Object implementation. Its containment guarantees must not be bypassed.
- The current worker's post-install verifier is named `verify_exact_user_install` and invokes WinGet with `--scope user`.
- The current approval model rejects Machine Scope: `VerifiedPackageEvidence.scope` is `Literal["user"]`.
- Discovery currently filters installers to User Scope. A Machine-only manifest therefore fails closed; the existing discovery test explicitly covers this case.
- Frontend runtime validation also accepts only `scope === 'user'`.

### Authentication and persistence

- `authenticator.py` protects the TOTP secret with Windows DPAPI using current-user scope.
- `step_up.py` and `totp.py` keep challenge/replay state in process memory. This is currently constrained by `main.py`'s single-worker enforcement. Do not assume these stores are cross-process or durable.
- `approval_reservation_store.py` stores immutable approval bindings and one-shot queue reservations in SQLite, with uniqueness/transactional state and platform storage protection.
- `auth_api.py` builds Google OIDC sessions and the existing TOTP services. Keep these paths backward-compatible.
- `security.py` permits the configured localhost frontend origins and has a narrowly scoped Google OAuth callback exception. New scope endpoints must remain behind the existing local API authorization and request-origin policy.

### Files confirmed relevant

Backend:
- `software_discovery.py`: WinGet manifest parsing and installer selection.
- `software_discovery_api.py`: authenticated discovery request/response.
- `software_install_api.py`: staged installer verification and proposal creation.
- `software_evidence.py`: staged-file, SHA-256, Authenticode, Publisher and evidence validation.
- `software_approval.py`: immutable evidence and approval digest.
- `software_approval_api.py`: exact-action TOTP challenge, confirmation, and durable reservation.
- `software_install_worker.py`: queue claim, execution coordination, and post-install verification.
- `winget_adapter.py`: exact manifest preparation and argument binding.
- `winget_execution.py`: WinGet process creation and containment.
- `process_containment.py`: Windows Job Object implementation.
- `approval_reservation_store.py`: durable one-shot approval and job state.
- `authenticator.py`, `auth_api.py`, `step_up.py`, `totp.py`: existing identity and step-up behavior.
- `security.py`, `main.py`, `runtime_diagnostics.py`: local security boundary, application lifecycle, and diagnostics.

Frontend:
- `src/frontend/src/app/chat/chat-api.ts`: API types and calls; currently models Scope as User only.
- `src/frontend/src/app/app.ts`: runtime response validation and software workflow state; currently rejects non-User Scope.
- `src/frontend/src/app/app.html`: workflow presentation and confirmation UI.
- `src/frontend/src/app/software-discovery.css`: discovery card styling.
- `src/frontend/src/app/app.spec.ts`: frontend behavior tests.

Tests:
- `tests/backend/test_software_discovery.py`: includes a Machine-only manifest rejection case.
- `tests/backend/test_software_install_api.py`: proposal and staged evidence tests.
- `tests/backend/test_security.py`: Origin/Host/local API security.
- `tests/backend/test_runtime_diagnostics.py`: diagnostics behavior.
- `src/frontend/src/app/app.spec.ts`: frontend validation and workflow tests.

## 3. Required architecture

The current worker is not a separate process: it is a thread in the Backend process. It must never be changed to request UAC for itself.

For Machine Scope, introduce a separately installed and signed Windows helper executable. The intended boundary is:

1. Frontend asks for discovery and explicitly selects a scope.
2. Backend re-fetches and validates the exact manifest, installer, version, architecture, Publisher, Authenticode signature, and SHA-256.
3. Backend binds Scope into immutable evidence and the approval digest.
4. User confirms the scope change and completes the existing exact-action step-up mechanism.
5. Backend persists the exact approval and creates a short-lived, one-use helper authorization.
6. Backend starts only the fixed, verified unelevated Launcher. The Launcher verifies the fixed Helper binary and requests UAC for that Helper only. Backend itself remains unelevated and never invokes `ShellExecute(runas)`.
7. Helper verifies its own signature/build identity, ticket integrity, expiry, nonce, approval digest, exact package facts, expected Windows SID, and elevated token.
8. Helper creates its own Job Object, creates the exact approved child process suspended, assigns it to the Job Object, and only then resumes it.
9. Helper returns a minimal authenticated result over a secured local IPC channel.
10. Backend independently verifies installed package ID, version, architecture, and Scope before reporting success.

The helper must not accept arbitrary executable paths, command lines, package IDs, versions, or arguments from the client. Those values must be derived from a signed/verified one-time authorization bound to the exact approval.

### Identity rule

A UAC prompt can be satisfied with alternate administrator credentials. That must not silently change the installation identity. The helper must compare its effective Windows SID with the SID bound to the original user session. A mismatch is rejected. If same-SID elevation cannot be obtained, Machine Scope remains unavailable.

### Containment rule

The existing Backend Job Object does not automatically contain a process tree created by a separately elevated helper. The helper must create and own its own Job Object. If WinGet or an installer can escape that Job Object, or if the helper cannot prove containment, Machine Scope must remain disabled. Do not fall back to `ShellExecute(runAs)` from the Backend or to an uncontained installer launch.

## 4. Scope and approval contract

Use the closed enum `user | machine` across server-side models. Never accept arbitrary Scope strings.

Discovery may report available options, but must not select Machine Scope automatically. A proposal request must include the explicitly selected Scope; Backend re-discovers the manifest and verifies that exactly one installer matches the selected architecture and Scope.

Scope is a material approval field. It must be included in:
- verified evidence;
- canonical approval digest;
- durable reservation binding;
- helper authorization ticket;
- execution arguments/manifest;
- post-install verification;
- diagnostics event metadata.

Any change to Scope invalidates the prior proposal and approval. A new proposal and a new exact-action TOTP approval are required.

Recommended Scope-change lifecycle:

`CREATED -> STEP_UP_PENDING -> CONFIRMED -> NEW_PROPOSAL_REQUIRED`

Reset/revoke must atomically invalidate the pending challenge and its nonce. It must not revoke or rewrite an already-running job; that job must be reconciled independently.

Recommended response errors include:
- `SCOPE_NOT_AVAILABLE`
- `SCOPE_MISMATCH`
- `SCOPE_CHANGE_EXPIRED`
- `SCOPE_CHANGE_REPLAYED`
- `SCOPE_CHANGE_CONFLICT`
- `STEP_UP_REQUIRED`
- `STEP_UP_INVALID`
- `STEP_UP_REPLAYED`
- `ADMIN_CONSENT_REQUIRED`
- `ADMIN_CONSENT_CANCELLED`
- `ELEVATION_IDENTITY_MISMATCH`
- `ELEVATED_HELPER_UNAVAILABLE`
- `PROCESS_CONTAINMENT_FAILED`
- `APPROVAL_BINDING_INVALID`

Error responses and logs must contain only a safe error code, generic message, and correlation ID. Never return credentials, TOTP, WebAuthn assertion, OAuth token, DPAPI material, or raw helper ticket.

## 5. UAC and process-token invariants

- Distinguish Administrators group membership from the current process's effective elevation state. A member account may run with a filtered token.
- The Backend and Agent must be verified unelevated before and after every Machine Scope attempt.
- UAC is requested only for the fixed helper executable, never for Python, FastAPI, the browser, or the Agent.
- Helper must prove elevated token state and same-user SID before consuming authorization or starting an installer.
- UAC cancellation means no installer process was started.
- Alternate credentials that change SID mean no installer process was started.
- A failed Job Object creation/assignment means the suspended child is terminated and never resumed.
- IPC loss or helper crash yields an unknown/reconciliation state, not success and not an automatic retry.

## 6. Replay, race, and persistence requirements

- Use a cryptographically random nonce and short expiry for each helper authorization.
- Consume the authorization atomically and exactly once in durable storage.
- Bind it to owner, session, SID, proposal, Scope, approval digest, package/version/architecture, installer digest, and action.
- Serialize Scope confirmation and reset through durable conditional state transitions; a Python lock alone is insufficient across restarts/processes.
- Reuse the existing durable reservation store only after confirming a schema migration strategy and its secure-storage adapter behavior.
- Current TOTP replay and step-up challenge stores are process-local. Preserve the single-worker restriction unless durable cross-process challenge/replay protection is implemented and separately tested.
- On Backend restart, expired or indeterminate helper operations must fail closed and be reconciled from actual installed state.
- Helper result processing must be idempotent.

## 7. Secret and audit hygiene

- Keep current-user DPAPI storage for the existing TOTP secret unchanged.
- The helper must not receive the DPAPI master secret or OAuth/TOTP secrets.
- Do not put tickets or secrets in process command lines, browser storage, diagnostics, or ordinary temporary files.
- Prefer secured IPC with explicit Windows ACLs and peer identity checks. The exact IPC transport is a design decision that must be validated on Windows.
- Record safe event metadata: Scope, package ID, version, architecture, approval digest, correlation ID, helper PID, SID-match result, UAC outcome, containment outcome, and final verification state.
- Never record TOTP, WebAuthn assertions, OAuth cookies/tokens, DPAPI plaintext/ciphertext, authorization MAC keys, or raw IPC payloads.

## 8. Windows-only verification gates

Machine Scope must remain unavailable until all of the following pass on supported Windows versions:

1. Standard User cannot install Machine Scope.
2. Admin member running with a filtered token leaves Backend and Agent unelevated.
3. UAC is shown only for the helper.
4. Accepting UAC with the same SID permits the helper path.
5. Alternate administrator credentials are rejected by SID mismatch.
6. Cancelling UAC starts no installer.
7. Helper signature and ticket tampering are rejected.
8. Expired and replayed tickets are rejected, including after Backend restart.
9. Helper-owned Job Object contains the WinGet/installer process tree; kill-on-close and timeout behavior are verified.
10. Helper IPC ACLs reject unrelated local users and spoofed peers.
11. Backend and Agent remain unelevated after success, failure, cancellation, timeout, and helper crash.
12. Installed package ID, version, architecture, and Scope are independently verified.
13. Google OAuth, localhost origin, existing TOTP, and DPAPI storage regression tests pass.
14. Logs and API errors contain no secret canaries.

## 9. Implementation sequence

### Phase A — safe discovery and approval contracts
- Extend discovery to enumerate User/Machine candidates without automatically selecting one.
- Add explicit Scope to proposal requests.
- Bind Scope into evidence and approval digest.
- Keep Machine proposal/execution blocked until the helper capability is present.
- Add backend/frontend contract tests and preserve existing User behavior.

### Phase B — durable Scope-change and helper authorization
- Add atomic Scope-change state and one-time helper ticket persistence.
- Bind identity/session/SID and approval digest.
- Add reset/revoke, expiry, replay, and concurrency tests.
- Do not add an alternate authentication system; use existing auth services and step-up policy.

### Phase C — signed helper and Windows containment
- Add helper build/sign/verification and secured IPC.
- Implement helper-owned Job Object and exact operation execution.
- Add Windows token, UAC, SID, IPC, and child-process integration tests.
- Keep Machine Scope disabled until all Windows gates pass.

### Phase D — UI and diagnostics
- Show User/Machine as explicit choices and explain the impact.
- Require a separate scope-change confirmation and exact-action approval.
- Show UAC cancellation, identity mismatch, containment failure, and unknown state distinctly.
- Keep diagnostics free of secrets and preserve the existing runtime diagnostics controls.

## 10. Preconditions before source changes

The following must be verified before implementation:
- Exact Windows packaging/build/signing pipeline for a helper executable.
- Whether a supported helper/IPC mechanism already exists elsewhere in the repository.
- Windows Job Object behavior for the actual WinGet version and each supported installer type.
- Secure-storage adapter ACL and database migration behavior.
- Whether the product supports only the same-user UAC consent path or needs a deliberately unsupported alternate-credential path.
- The existing frontend component/template flow for Scope selection and confirmation.

Until these are verified, Machine Scope must remain fail-closed. No Backend/Agent elevation, no silent Scope substitution, no UAC fallback, and no merge without explicit approval.
