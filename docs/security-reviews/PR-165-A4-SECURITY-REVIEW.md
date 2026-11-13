# PR-165 — Independent A4 Security Review

**Reviewer role:** Independent A4 Security Architect / Security Reviewer (automated reviewer, not a human A4 sign-off)
**Review date:** 2026-11-13
**Pull request:** <https://github.com/keng-lap/ai-agent-pc-automation/pull/165>
**Branch reviewed:** `security/P6-601-windows-secret-store-recovery` → `main`
**PR state at review time:** open, **draft**, not merged, `mergeable_state: clean`
**Base commit (merge base with `main`):** `96e4d0dc5ad6d920438056e33909d615937934fd`

## 1. Review status

**PASS WITH CONDITIONS**

No Critical or High severity vulnerability was verified. Two Medium findings and two Low findings are recorded; each is either a documentation/implementation inconsistency in a security control or a bounded operational weakness, not an authentication or authorization bypass. Conditions are listed in §8.

This review does **not** approve the PR, does not merge it, does not change draft status, and does not enable any runtime capability.

## 2. Exact source commit reviewed

| Item | Value |
|---|---|
| Requested review HEAD | `e0f8c4b668012b2c5547f6523bd7b177506815bb` |
| Actual PR HEAD at review time | `e0f8c4b668012b2c5547f6523bd7b177506815bb` |
| Match | **Exact match — no divergence** |
| Local branch used | `security/P6-601-windows-secret-store-recovery` at `e0f8c4b` |
| Base commit (`main`) | `96e4d0dc5ad6d920438056e33909d615937934fd` |
| Diff reviewed | 24 files, +1847 / −64 |

The PR head matched the expected SHA exactly, so the requested source version is the version reviewed. No substitution of a different revision occurred.

## 3. Review scope and files inspected

### 3.1 Windows secret storage
- `src/backend/agent_backend/windows_secret_storage.py` (new, 426 lines) — read in full.
- `tests/backend/test_windows_secret_storage.py` (new) — read in full.
- `src/backend/agent_backend/authenticator.py` — read in full (DPAPI adapter and store).
- `tests/backend/test_authenticator.py` — read in full.
- `src/backend/pyproject.toml` — `pywin32>=311; sys_platform == 'win32'` addition.

### 3.2 Authenticator and recovery
- `src/backend/agent_backend/oidc.py` — read in full.
- `src/backend/agent_backend/auth_api.py` — read in full.
- `src/backend/agent_backend/totp.py` — read in full.
- `src/backend/agent_backend/step_up.py` — read in full, including the PR diff.
- `src/backend/agent_backend/auth_audit.py` — read, including the PR diff.
- `src/backend/agent_backend/main.py`, `src/backend/agent_backend/config.py` — read for route wiring, middleware and configuration gates.
- `src/backend/agent_backend/plan_api.py` — inspected for the step-up / secret-load enforcement path (unchanged by this PR).
- `src/backend/agent_backend/security.py` — inspected for host/Origin/local-agent-token enforcement (unchanged by this PR).
- `tests/backend/test_auth_api.py`, `tests/backend/test_oidc.py`, `tests/backend/test_security.py`, `tests/backend/conftest.py` — read, including diffs.

### 3.3 Security boundaries
- `src/backend/agent_backend/platform_storage.py` — Windows job-store gate inspected (unchanged by this PR).
- `.github/workflows/windows-authenticator.yml`, `.github/workflows/windows-process-containment.yml`, `.github/workflows/ci.yml` — inspected.
- Grep for `subprocess`, `os.system`, `Popen`, `shell=True`, `powershell`, `winget`, `WinExec`, `ShellExecute`, `exec(`, `eval(` across all changed backend modules: **no matches**.

### 3.4 Documentation
- `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md` (new) — read in full.
- `docs/P6-601-BACKGROUND-JOB-ARCHITECTURE.md` — diff inspected.
- `docs/PHASE-6.md` — inspected for P6-601 / acceptance statements.
- `docs/P6-601-TRUSTED-SOFTWARE-DISCOVERY.md`, `docs/P6-601-A4-REVIEW-PACKET.md`, `docs/SECURE-DEVELOPMENT-STANDARD.md` — inspected for the governing requirements applied in this review.

### 3.5 Out of scope / not line-reviewed
- Frontend changes (`src/frontend/src/app/*`) were read only at diff level to confirm no secret material, QR payload logging, or auth-boundary weakening was introduced. No frontend security review is claimed.
- `tests/backend/test_jobs_api.py`, `tests/backend/test_software_approval_api.py`, `tests/backend/test_auth_audit.py` diffs were inspected only for scope (test-harness adaptation to the new auth dependency).

## 4. Executive summary

This PR introduces a handle-based Windows secret-file adapter with a current-user-only DACL and DPAPI current-user protection, and adds a Google-reauthenticated authenticator replacement flow. The core security design is sound:

- Google OIDC remains the only primary authentication mechanism; TOTP is step-up only.
- Fresh reauthentication uses `prompt=login` and `max_age=0`, and the resulting ID token's `auth_time` is validated against a 300-second bound (`oidc.py:345-353`).
- The fresh-authentication grant is bound to a live server-side session and is consumed atomically and exactly once (`oidc.py:552-591`, `auth_api.py:319-320`, `auth_api.py:414-415`).
- The old TOTP secret remains valid and loadable until a replacement is confirmed; only then is the file replaced, and the TOTP time-step is blocked afterwards (`authenticator.py:466-530`).
- The Windows adapter pins every parent directory handle without `FILE_SHARE_DELETE`, rejects reparse points at every component, verifies the owner SID, applies a protected single-ACE DACL, and performs all file I/O through verified handles (`windows_secret_storage.py:158-296`).
- Fail-closed behavior is consistent: missing pywin32, wrong owner, reparse point, non-owner-only DACL and oversized/corrupt payloads all raise, and the risky operations surface 503 rather than proceeding.
- No shell, PowerShell, CMD, script, WinGet or installer execution was added anywhere in the diff.

The two Medium findings are documentation/implementation inconsistencies in the Windows replacement and DACL-repair controls, plus two Low-severity operational weaknesses (temporary-file residue, and a state/audit divergence when session rotation fails after persistence). None of them grants an attacker new authority; they affect durability and recoverability of the step-up factor.

**Windows 11 Home acceptance was NOT performed and remains outstanding.**

## 5. Findings

Severity levels used: Critical / High / Medium / Low / Informational. Each finding states its evidence basis so that static-analysis findings are not confused with runtime-verified ones.

### F-01 — Medium — Documented replacement primitive (`MoveFileExW` + `WRITE_THROUGH`) is not implemented

**Evidence**
- Documented requirement: `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:41` states "Replacement writes a new protected file in the same secured directory and uses `MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`, then reopens and verifies the replacement."
- Implementation: `src/backend/agent_backend/windows_secret_storage.py:365-412` performs the replacement with `SetFileInformationByHandle(..., FileRenameInfo, ...)` and `ReplaceIfExists = 1` (`windows_secret_storage.py:398-411`). There is no `MoveFileExW` call and no `MOVEFILE_WRITE_THROUGH` equivalent anywhere in the module (grep for `MoveFileEx` and `WRITE_THROUGH` in `src/backend/agent_backend/` returns no implementation hit).
- The code comment at `windows_secret_storage.py:365-369` explains the divergence, and `FlushFileBuffers` is only applied to the temporary file contents (`windows_secret_storage.py:316`), not to the rename's directory metadata.

**Attack scenario**
Not an attacker-driven bypass. On an unclean shutdown or power loss immediately after a successful recovery replacement, the renamed directory entry (and possibly the new file's metadata) may not be durable, so the previous TOTP secret can reappear after restart while the user believes the replacement succeeded. The user's old authenticator then silently becomes valid again.

**Impact**
The documented durability/atomicity control is not the control the code actually provides. Integrity of the "replacement completed" statement to the owner is weakened; the documented and reviewed behaviour cannot be relied upon as written.

**Remediation**
Either implement the documented durability semantics (write-through rename, or `FlushFileBuffers` on the parent directory handle after `SetFileInformationByHandle`), or correct `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:41` to describe the actual `FileRenameInfo` handle-relative rename and state explicitly that directory-entry durability is best-effort. Whichever is chosen, the Windows CI test set should assert the chosen behaviour.

**Additional documentation inconsistency in the same document:** `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:14-15` describes enrollment as "the backend starts a fresh Google OIDC transaction" as part of the enrollment call. In the implementation, `POST /api/authenticator/enrollment` (`auth_api.py:304-340`) does **not** start an OIDC transaction; the frontend must first call `GET /api/auth/google/reauth/start` (`auth_api.py:192-208`) and complete `/auth/google/callback`. The security outcome is equivalent (the grant is still required and one-time), but the documented flow does not match the implemented flow.

### F-02 — Medium — Documented automatic DACL hardening of an existing secret *file* is not implemented; a bad file DACL becomes an unrecoverable step-up state

**Evidence**
- Documented requirement: `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:48` states "A current-user-owned directory/file with a bad DACL is hardened automatically; wrong-owner or reparse-point paths remain rejected."
- Implementation: only the **final directory** is repaired. `windows_secret_storage.py:203-211` calls `_set_owner_only_dacl(...)` for the final directory when the owner already matches. For the **secret file**, `windows_secret_storage.py:288-295` explicitly refuses repair: "Existing secret files are immutable from a trust-policy perspective: verify their ACL, but never attempt to repair it."
- Consequence chain, traced end to end:
  1. A secret file whose DACL is not exactly one allow-ACE for the current SID (for example after a backup/restore, a copy, or a tool that adds an inherited ACE) makes `WindowsSecretFile.exists()` raise `WindowsSecretStorageError` (`windows_secret_storage.py:297-304` → `_open_file` → `_verify_owner_only_dacl`).
  2. `EncryptedTotpSecretFileStore.is_configured()` wraps that into `SecretStoreError` (`authenticator.py:155-168`).
  3. `POST /api/authenticator/enrollment` and `POST /api/authenticator/recovery` both call `is_configured()` first and return **503 "Authenticator storage unavailable."** (`auth_api.py:316-322`, `auth_api.py:411-417`).
  4. `EncryptedTotpSecretFileStore.replace()` → `WindowsSecretFile.replace()` re-opens the destination with `create=False` for verification (`windows_secret_storage.py:343-347`) and therefore also fails closed.
  5. Result: the documented recovery path ("A confirmed replacement can atomically replace a corrupt payload", `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:49`) cannot repair this specific state, and every high-risk step-up operation returns 503 permanently until an operator manually fixes the ACL.

**Attack scenario**
An attacker who can alter the ACL of the file but not its contents (for example a same-user or backup agent, or an administrative tool applying inheritance) can permanently disable step-up approval without needing the TOTP secret or the DPAPI key. This is a denial of the step-up capability, not an authentication bypass: ordinary Google sign-in and read-only job status remain available, and approval remains blocked (fail-closed).

**Impact**
Permanent step-up lockout that contradicts an explicit "lockout prevention" claim in the reviewed security documentation. Availability impact on a security control; no authority escalation.

**Remediation**
Choose one and document it:
- Implement a bounded repair for an existing secret file (set the protected owner-only DACL only when the owner SID already equals the current user, then re-verify), with an audit event recording that a repair occurred; or
- Keep the current fail-closed behaviour but (a) correct `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:48-49` so it no longer claims automatic file hardening, (b) add a documented operator procedure for ACL repair, and (c) verify that the documented corrupt-payload recovery path is the only recovery path that exists.

### F-03 — Low — Replace-failure temporary files are never cleaned up, and no maintenance pass exists

**Evidence**
- `windows_secret_storage.py:332-340` creates `.{name}.{32 hex}.tmp` in the secured directory.
- On failure, the exception path at `windows_secret_storage.py:415-421` deliberately does not delete it, with the comment "the next successful maintenance pass can report it for manual cleanup".
- No such maintenance pass exists anywhere in the repository (grep for `.tmp` handling in `src/backend/agent_backend/` returns no cleanup routine), and `EncryptedTotpSecretFileStore.replace()` (`authenticator.py:228-289`) does not clean up either.
- A failed `create_exclusive` (`windows_secret_storage.py:306-316`) also leaves the created file behind if the write is short (`windows_secret_storage.py:313-315`), producing a truncated envelope.

**Attack scenario**
Repeated failed recoveries accumulate DPAPI-ciphertext files inside the protected directory. A same-user attacker cannot decrypt them (DPAPI current-user scope is the same user, so this is not a confidentiality break against the documented threat model), but they are undocumented residue that is never enumerated, never reported, and never removed.

**Impact**
Bounded storage residue and operator confusion; a truncated envelope blocks enrollment (409) and makes recovery the only path. No confidentiality or integrity bypass within the documented threat model.

**Remediation**
Either delete the temporary file in the failure path (safe: it is a random name inside a pinned, DACL-restricted directory), or implement the referenced maintenance reporting and document it in the security documentation.

### F-04 — Low — Session rotation failure after secret persistence yields HTTP 401 with a changed security state

**Evidence**
- `auth_api.py:353-367`: `services.enrollment.confirm(...)` is called first and persists/replaces the secret; only afterwards is `services.sessions.rotate(token)` called, and `None` raises `401 "Authentication session expired."` (`auth_api.py:366-367`).
- The success audit event is recorded only after rotation (`auth_api.py:377`).
- `ApplicationSessionStore.rotate()` returns `None` when the presented token is no longer resolvable or has expired (`oidc.py:593-640`).

**Attack scenario**
Requires a token that expires exactly between confirmation and rotation, or a concurrent sign-out/rotation. The client is told the operation failed while the authenticator secret has already been enrolled or replaced; no success audit event is written even though the security state changed.

**Impact**
State/audit divergence and a misleading client result. The new secret is the enrolled one, the old step-up grant was already consumed, and no privilege is retained or escalated.

**Remediation**
Rotate (or pre-validate the session) before persisting, or emit an explicit audit event for "persisted but session rotation failed" and return a result that reflects the persisted state. Document the ordering guarantee.

### F-05 — Informational — `tests/backend/conftest.py` installs a global `require_session` dependency override

**Evidence**
`tests/backend/conftest.py:15-23` overrides `require_session` on the module-level `app` for every test that imports it, substituting a synthetic owner/session.

**Assessment**
The comment states that auth-specific tests build their own app and therefore still exercise the real dependency, and `tests/backend/test_auth_api.py` does exactly that. However, a global override on the shared `app` object can mask an authentication regression in any future test that imports the global app, and it is a test-integrity risk rather than a production change.

**Remediation**
Scope the override to a fixture with explicit use, or assert in a dedicated test that the real dependency still fails closed on the global app.

### F-06 — Informational — DPAPI plaintext handling has no memory zeroization

**Evidence**
`authenticator.py:83-130`: plaintext is passed in a Python `bytes` object, copied into `ctypes.create_string_buffer(value)` (`authenticator.py:88`), and the DPAPI output buffer is released with `LocalFree` (`authenticator.py:137-145`) without `RtlSecureZeroMemory`.

**Assessment**
Standard CPython limitation. Copies of the TOTP secret (and the decrypted envelope) can persist in process memory until garbage collection and may appear in a crash dump. The documented threat model already excludes same-user malware (`docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:58`), so this does not weaken a documented guarantee, but it is worth recording.

### No other verified findings

No verified Critical or High finding exists in this PR. In particular, the following were actively looked for and **not** found:

- A path by which the frontend, model output or an approval could mint, replace or read the TOTP secret without a fresh, one-time Google authentication grant.
- A path by which a bad DACL, wrong owner, reparse point or corrupt envelope results in an unverified read or an unprotected write.
- Any new shell/PowerShell/CMD/script/installer invocation, WinGet invocation, dynamic import, or host mutation in the changed code.
- Any weakening of the route-level authorization dependencies, the loopback host check, the Origin allow-list, or the local-agent-token requirement.

## 6. Security control assessment

Legend: **PASS** / **FAIL** / **NOT VERIFIED**. "Evidence basis" distinguishes runtime evidence from static reading.

### 6.1 Windows secret storage

| Control | Result | Evidence basis |
|---|---|---|
| DPAPI current-user protection (no `CRYPTPROTECT_LOCAL_MACHINE`, `UI_FORBIDDEN`) | PASS | `authenticator.py:57, 83-130`; windows-dpapi CI job on `windows-latest` passed |
| Owner SID verification on every open | PASS | `windows_secret_storage.py:93-155, 203-211`; Windows CI tests |
| DACL construction (protected, exactly one allow ACE, current SID, `FILE_ALL_ACCESS`) | PASS | `windows_secret_storage.py:112-129`; extra-ACE rejection test passed on Windows CI |
| DACL enforcement on every open (read and write) | PASS | `windows_secret_storage.py:288-295`; `test_windows_secret_file_rejects_extra_dacl_ace_for_verified_owner` passed on Windows CI |
| Automatic hardening of an existing file DACL as documented | **FAIL** | F-02; `windows_secret_storage.py:288-295` vs `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:48` |
| Reparse-point rejection on every path component | PASS | `windows_secret_storage.py:82-90, 158-199`; ancestor and file reparse tests passed on Windows CI |
| Directory/file handle security (`FILE_FLAG_OPEN_REPARSE_POINT` + `BACKUP_SEMANTICS`, all I/O via handle) | PASS | `windows_secret_storage.py:168-186, 258-270, 297-330` |
| Handle sharing modes (directories: read+write, no delete; file: read only) | PASS | `windows_secret_storage.py:176, 264`; rename-denied test passed on Windows CI |
| TOCTOU resistance for path replacement | PASS | Pinned parents without `FILE_SHARE_DELETE` (`windows_secret_storage.py:176, 214-252`) plus handle-relative rename; residual same-user risk is documented |
| Atomic replacement | PASS | `FileRenameInfo` + `ReplaceIfExists` (`windows_secret_storage.py:398-411`) is a single atomic rename |
| Replacement durability as documented (`WRITE_THROUGH`) | **FAIL** | F-01; `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:41` vs `windows_secret_storage.py:365-412` |
| Cleanup of temporary/failed artifacts | **FAIL** | F-03; `windows_secret_storage.py:415-421`, no maintenance pass exists |
| Fail-closed on unavailable APIs / untrusted paths / corrupt payload | PASS | `windows_secret_storage.py:50-61, 86-90, 143-155`; `authenticator.py:155-168, 291-350`; tests |
| Bounded secret size (≤16 KiB, non-empty) | PASS | `windows_secret_storage.py:33, 306-311, 318-330` |
| Non-Windows fallback cannot write unprotected secret material | PASS | `WindowsDpapiProtector._transform` rejects non-Windows (`authenticator.py:72-81`), so `protect()` fails before any write |

### 6.2 Authenticator and recovery

| Control | Result | Evidence basis |
|---|---|---|
| Google OIDC remains primary authentication | PASS | `auth_api.py:116-129`; `main.py` route dependencies; tests |
| Fresh Google reauthentication for enrollment and recovery | PASS | `auth_api.py:192-208, 319-320, 414-415` |
| `prompt=login` and `max_age=0` only for reauthentication | PASS | `oidc.py:233-236`; `test_begin_login_uses_code_flow_pkce_nonce_and_minimal_scopes`, `test_begin_login_can_request_fresh_authentication_only_when_needed` |
| OIDC transaction binding (state + nonce + PKCE, one-time, bounded, 300s TTL) | PASS | `oidc.py:70-155, 217-239`; OIDC tests |
| Five-minute fresh-proof expiry and one-time use | PASS | `oidc.py:32-33, 345-353, 552-591`; `test_totp_enrollment_requires_recent_google_reauthentication`, `test_fresh_google_auth_grant_is_consumed_once_for_enrollment` |
| Session rotation after sensitive enrollment | PASS | `oidc.py:593-640`; `auth_api.py:366, 377` — ordering caveat recorded as F-04 |
| TOTP enrollment and confirmation (`is_configured` gate, 5-attempt cap, 300s TTL, owner binding, replay consumption) | PASS | `authenticator.py:400-530`; enrollment tests |
| Authenticator replacement flow exists and is owner-bound | PASS | `authenticator.py:395-399, 466-530`; `auth_api.py:398-448` |
| Old TOTP remains active until replacement confirmed | PASS | `authenticator.py:518-524`; `test_recovery_replaces_secret_only_after_new_authenticator_is_confirmed`, `test_totp_recovery_replaces_lost_authenticator_after_google_reauth` |
| Replay prevention for step-up and enrollment | PASS (single process) | `totp.py:132-190`, `step_up.py:158-233`; process-local only — multi-worker is blocked by `main.py:31-65` |
| Rate limiting | PASS | 5 failed enrollment attempts (`authenticator.py:38, 497-515`), 5 failed step-up attempts and a 5-per-300s owner/session lock (`step_up.py:20-25, 168-232`), 64 pending OIDC transactions (`oidc.py:30, 138-140`) |
| Recovery abuse and race resistance | PASS (with conditions) | Grace period preserved, single use, owner binding, atomic replace; depends on process-local state (conditions in §8) |

### 6.3 Security boundaries

| Boundary | Result | Evidence basis |
|---|---|---|
| Google OIDC remains primary authentication | PASS | Only `google` routes create sessions (`auth_api.py:209-262`) |
| TOTP is step-up only for high-risk operations | PASS | Enrollment/recovery require a live Google session plus a fresh grant; `plan_api.py:255-269, 335-345` loads the secret and requires a challenge before approval |
| Storage failures fail closed | PASS | `auth_api.py:316-322, 333-341, 411-417`; `plan_api.py:258-269, 333-341` return 503 and never proceed |
| No arbitrary shell / PowerShell / CMD / script execution | PASS | Grep of all changed modules; no `subprocess`, `os.system`, `Popen`, `shell=True`, `exec(`, `eval(` |
| No WinGet invocation or installer execution | PASS | No WinGet/installer call in the diff; `windows-winget-adapter` CI job unchanged and green |
| No unapproved host mutation | PASS | PR adds no execution path; job store and approval handlers are unchanged except harness updates |
| Approval cannot bypass backend authorization | PASS | `/api/*` requires the local agent token (`security.py:71-77`), Origin allow-list (`security.py:54-69`), and `require_session` on chat/plan/discovery/approval routers (`main.py`); jobs routes enforce it per handler (`jobs_api.py:52-58`) |
| Windows Job Store DACL/handle gate remains closed | PASS | `platform_storage.py:122-126` still raises on `win32`; file unchanged by this PR; `job_store.py:87-89` unchanged |

## 7. Missing evidence

Recorded explicitly so that no unverified area is presented as a PASS.

1. **Windows 11 Home acceptance was NOT performed.** CI ran on GitHub-hosted `windows-latest` runners, not on the target Windows 11 Home machine. `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:57` itself states that hosted-runner tests do not replace acceptance on the target machine. **This gate remains outstanding.**
2. **Windows CI job logs could not be retrieved.** The commit check API reports the jobs and steps, but log download returns `403 "Must have admin rights to Repository."` Step-level conclusions are therefore the strongest CI evidence available to this reviewer; the individual test names counted inside the Windows run are not independently confirmed by the reviewer.
3. **No runtime execution of any Windows-specific control in this review environment.** The review sandbox is Linux; the five Windows-only tests in `tests/backend/test_windows_secret_storage.py` and the DPAPI integration test are skipped locally. All Windows-specific PASS results rest on (a) static code reading and (b) the green CI steps named below, not on observation by this reviewer.
4. **No real Google IdP end-to-end ceremony.** OIDC tests are deterministic fakes (`FakeOidc`, injected `token_verifier`). `prompt=login`/`max_age=0` behaviour against Google, and the presence/accuracy of `auth_time` in Google's ID token under all account states, are verified by specification and code inspection, not by a live sign-in in this review.
5. **No fuzzing, penetration testing or attack-simulation run** against the new endpoints.
6. **Frontend security review not performed** (diff-level inspection only). No claim is made about the recovery UI's correctness beyond the absence of obvious secret/PII exposure in the diff.
7. **Process-local security state.** Replay guards, OIDC transactions, sessions and step-up challenges are in-memory; multi-worker operation is rejected (`main.py:31-65`) but no shared durable store exists. This is a documented limitation, not verified remediation.

### Evidence actually observed by this reviewer

- `pytest tests/backend -q` on the reviewed commit: **513 passed, 9 skipped** (skips include all Windows-only tests).
- `pytest tests/backend/test_oidc.py test_authenticator.py test_auth_api.py test_windows_secret_storage.py test_security.py -q`: **110 passed, 6 skipped**.
- `ruff check agent_backend ../../tests/backend` executed from `src/backend` (the exact CI command): **All checks passed**.
- GitHub check runs for `e0f8c4b668012b2c5547f6523bd7b177506815bb`: **10 of 10 completed with `success`**, including `windows-dpapi` (job `131950409493`, runner label `windows-latest`; steps "Test Windows DPAPI authenticator storage" = success) and `windows-process-containment` (job `131950410256`, `windows-latest`; step "Test Windows authenticator storage and DPAPI", which runs `test_authenticator.py`, `test_auth_api.py` and `test_windows_secret_storage.py`, = success).
- PR metadata: `state=open`, `draft=true`, `merged=false`, `mergeable_state=clean`, head SHA matching the expected review SHA.

## 8. Required actions before merge

Conditions of this PASS WITH CONDITIONS. None of these authorizes merge; merge remains a separate Product Owner decision.

1. **Resolve F-01.** Either implement write-through/durable replacement, or correct `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:41` to describe the implemented `FileRenameInfo` rename and its durability characteristics. Also correct the enrollment-flow description at lines 24-27 to match the implemented reauth-then-enroll sequence.
2. **Resolve F-02.** Either implement bounded, audited DACL repair of an existing secret file, or correct `docs/P6-601-WINDOWS-AUTHENTICATOR-SECURITY.md:48-49` and add a documented manual-repair procedure. In either case, state plainly that a bad file DACL blocks enrollment, recovery and step-up until repaired.
3. **Resolve or explicitly accept F-03** (temporary/partial file residue and the non-existent "maintenance pass").
4. **Resolve F-04** (rotation after persistence) or document the ordering guarantee and the resulting audit gap.
5. **Complete Windows 11 Home acceptance testing on the target machine** with recorded evidence (owner-only DACL observed, DPAPI round-trip, reparse-point rejection, enrollment, recovery, step-up), and attach it to the PR or a linked document.
6. **Obtain the project's required independent A4 sign-off.** This report is an independent automated review and must not be used to self-certify the implementer's work under `docs/SECURE-DEVELOPMENT-STANDARD.md`; if the project requires a named human A4 approval, it is still required.
7. **Keep the PR in draft and unmerged** until actions 1-6 are satisfied and the PR is rebased/retested against `main` at merge time.

Optional hardening, not blocking: scope the `tests/backend/conftest.py` dependency override (F-05) and note the DPAPI memory-hygiene limitation (F-06) in the security documentation.

## 9. Independent final recommendation

**PASS WITH CONDITIONS — do not merge yet.**

The security architecture is coherent and the primary controls that matter (Google-only primary authentication, one-time fresh-authentication proof, old-TOTP-still-valid-until-confirmed, fail-closed storage, handle-based DACL enforcement, no execution surface) are implemented and, for the Windows-specific parts, exercised by green Windows CI jobs at the reviewed commit. No Critical or High vulnerability was verified.

The blocking conditions are correctness and honesty of the security documentation versus the code (F-01, F-02), the outstanding Windows 11 Home acceptance gate, and the absence of a human independent A4 sign-off. The two Medium findings do not create an attacker path to authenticate, escalate, or execute code; they make a documented guarantee untrue and can leave the step-up factor in a state the documentation says is impossible.

This review approves nothing and enables nothing. It records evidence, findings and required remediation only.

---

### Appendix A — Commit SHA and scope of this review

- Reviewed source: `e0f8c4b668012b2c5547f6523bd7b177506815bb` (exact match to the requested HEAD).
- Diff base: `96e4d0dc5ad6d920438056e33909d615937934fd` (`main`).
- This document is the only repository change made by this review; no application source, test, workflow, configuration or existing documentation was modified.

### Appendix B — How each claimed result was obtained

| Result | Basis |
|---|---|
| PASS (Linux-executable behaviour) | Tests executed by this reviewer |
| PASS (Windows-only behaviour) | Static reading of the cited lines + green Windows CI step named above; not observed in this review environment |
| FAIL | Documented requirement compared against cited implementation lines |
| NOT VERIFIED | No execution path, artifact, or CI step available to this reviewer |
