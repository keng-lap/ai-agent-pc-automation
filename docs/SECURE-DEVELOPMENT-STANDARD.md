# Secure Development Standard

**Status:** Proposed repository-wide engineering policy; binding after Product Owner review and merge. Applies to backend, frontend, Windows integration, providers, CI, and AI-assisted changes.

## Purpose and authority
Prevent defects by making threat analysis, secure design, implementation controls, negative tests, and independent review part of normal development. This reduces risk; it does not guarantee defect-free software. This standard does not authorize real PC-changing execution, new providers/data flows, persistence, LAN access, or any capability not separately approved. Existing phase decisions and capability-specific approvals remain authoritative.

## Non-negotiable project boundaries
- Windows 11 local machine only; preserve loopback-only binding and existing Host, Origin, local-token, and request-size protections.
- No LAN exposure, public tunnel, cloud control plane, mobile remote PC control, or remote machine selection.
- No unrestricted shell, PowerShell, CMD, script runner, arbitrary executable, general-purpose terminal, dynamic import, eval, model-authored command, or model-supplied handler name.
- Tool IDs, schemas, policy, permissions, and handler mappings are backend-owned and fixed.
- Unknown tools, malformed/extra parameters, policy uncertainty, missing authentication/user presence, stale/mismatched/replayed approvals, audit failure, and handler/catalog drift fail closed.
- Frontend state and model/provider output are never authorization authorities.
- Machine-changing capabilities remain mock/dry-run until their individual gates are complete and separately approved.
- Use synthetic fixtures, mocks, spy handlers, and isolated temporary directories. Never inspect or mutate the user's live PC during planning or tests.
- Do not add persistence, providers, credentials, external destinations, or data flows without explicit approval. Do not persist chat messages, prompts, provider responses, or unrestricted transcripts.

## Required workflow before implementation
1. **Requirement/scope:** state outcome, components, non-goals, prohibited side effects, applicable decisions, findings, and capability gates. Reconcile conflicting source-of-truth documents first.
2. **Trust boundaries/data flow:** identify actors, assets, entry points, secrets, privileged operations, and external destinations. Trace untrusted input through validation, policy, approval, dispatch, side effect, and audit.
3. **Threat model:** consider STRIDE where relevant, plus abuse cases, race/TOCTOU, replay, confused deputy, fail-open, partial failure, crash/restart, clock behavior, and resource exhaustion. Use docs/templates/THREAT-MODEL-TEMPLATE.md.
4. **Secure design:** define testable invariants and rejection behavior before implementation. Specify canonicalization, validation, authorization, ownership binding, expiry, concurrency, resource bounds, logging/redaction, and recovery as applicable.
5. **Test design:** define positive, negative, boundary, abuse, regression, and failure-injection tests. Prove denied paths cannot reach side-effect handlers using spies/fakes and zero-call assertions. Identify required platform-specific CI.

If a security property cannot be stated and tested, stop and report BLOCKED.

## Secure implementation requirements

### Input and API boundaries
- Validate external input at backend boundaries with strict schemas, bounds, and explicit unknown-field behavior.
- Canonicalize at one defined boundary; authorize the same immutable canonical values later consumed by the handler.
- Never trust client-supplied identity, role, risk, permission, handler, path, executable, or approval status.
- Prevent ambiguous parsing, unsafe deserialization, path traversal, injection, open redirects, and uncontrolled URL/host selection.
- Bound request size, timeouts, concurrency, and resource consumption.

### Authentication, sessions, approvals
- Bind sessions and approvals to intended owner, session, exact tool ID, canonical parameters, and target.
- Enforce expiry, one-time consumption, replay resistance, and concurrency/atomicity at the authoritative backend boundary.
- Treat clock rollback, process restart, multiple workers, and storage loss as explicit threats.
- Never return cached approval success before fresh required user-presence proof.
- Missing authentication, ambiguous state, storage failure, or required audit failure must not grant access.

### Files, secrets, Windows APIs
- Never assume POSIX mode bits such as 0600 establish a restrictive Windows DACL.
- Define and verify Windows ACL, ownership, inheritance, reparse-point, path canonicalization, and handle-based access semantics for sensitive files.
- Avoid check-then-open path patterns. Where supported, open with reparse-point protections, validate the opened handle, and perform I/O through that same handle.
- Do not change ACLs on arbitrary user-configured directories without an explicit ownership/scope policy.
- Minimize plaintext secret lifetime; never log secrets, tokens, OTPs, key material, or secret-bearing exception text.
- Release native resources on every success/failure path; test native allocation/free behavior with fakes and Windows CI.

### Process and software execution
- No arbitrary command construction or execution.
- Use fixed backend-owned adapters with typed arguments and explicit executable/source constraints.
- Verify software origin, publisher/signature, artifact identity, redirects, authoritative hashes, and TOCTOU boundaries before separately authorized execution.
- Package names, search results, filenames, and model suggestions are not trust evidence.
- Installation/removal remains Dry Run until its own capability approval and gates pass.

### Audit, privacy, errors
- Security-critical decisions must not continue silently when required audit persistence fails.
- Record minimal allowlisted events; redact credentials, secrets, prompts, and sensitive machine inventory.
- Bound event/output sizes, retention, and storage usage.
- Distinguish accepted, started, completed, failed, cancelled, and unknown/reconciliation states.
- Return safe user-facing errors; keep diagnostics only in controlled, redacted logs.

### Concurrency and background jobs
- Define state machines and legal transitions explicitly.
- Use atomic approval consumption and job creation where required.
- Define idempotency, worker lease/fencing, retry policy, cancellation, crash recovery, and reconciliation before side effects.
- Never retry side-effecting actions unless idempotency and duplicate-effect behavior are proven.
- Define scheduler timezone, DST, misfire, overlap, and per-run approval semantics.

### Frontend
- Treat the browser as an untrusted presentation layer. Disabled buttons, hidden controls, route guards, and client state are not authorization.
- Display the exact action, target, and parameters being approved.
- Prevent XSS and unsafe HTML/URL handling; use appropriate browser security controls.
- Do not store secrets or authoritative approval state in browser storage.

## Required security tests
Cover applicable cases for each boundary:
- Valid request succeeds only through the intended fixed path.
- Missing, malformed, extra, oversized, non-canonical, and boundary-value input is rejected.
- Wrong owner/session/target/tool/parameter binding is rejected.
- Expired, replayed, concurrently consumed, stale, or modified approval is rejected.
- Auth disabled, missing user presence, storage unavailable, audit unavailable, or policy error fails closed.
- Denied requests make zero calls to side-effect handlers.
- Path traversal, symlink/reparse point, race/TOCTOU, and unsafe permissions are rejected where files are involved.
- Restart, clock rollback, worker duplication, crash, timeout, cancellation, and partial failure are covered where lifecycle behavior is involved.
- Logs and API responses do not disclose secrets or sensitive data.
- Every fixed security finding has a regression test.

Use synthetic data and isolated fixtures. Platform-specific behavior must run on the matching CI platform; a mock is not proof of native Windows behavior.

## Verification before PR
- Read applicable source-of-truth documents and inspect the complete diff.
- Run documented formatting, lint, type, unit, integration, frontend, and build checks applicable to changed files.
- Run security-specific negative and regression tests.
- Run configured dependency, secret, and static-analysis checks; report unavailable checks honestly.
- Verify platform-specific behavior on the relevant runner, especially Windows APIs, DPAPI, and ACL behavior.
- Check for scope expansion, generated artifacts, secrets, skipped checks, weakened assertions, and unrelated edits.
- Report exact commands, results, skipped checks, and evidence commit/CI run.

PASS means completed successfully. Queued/in-progress is PENDING; failed is FAIL; not run/unavailable is NOT VERIFIED. Never describe NOT VERIFIED as PASS.

## Independent review and severity
Security-sensitive changes require review by someone other than the implementer. The reviewer inspects source diff, threat model, tests, and evidence; a checklist or AI assertion alone is not independent verification.

- **Critical:** practical unauthenticated/unauthorized compromise, arbitrary code execution, or equivalent catastrophic boundary failure.
- **High:** material privilege escalation, secret compromise, approval bypass, or security-control bypass.
- **Medium:** meaningful weakness with constrained exploitability or impact; label defense-in-depth concerns clearly.
- **Low:** limited-impact hardening or maintainability issue with security relevance.
- **Informational:** observation without a demonstrated security defect.

Every finding states evidence, preconditions, impact, exploitability/confidence, affected paths, fix, and regression test. Do not label design concerns as exploitable vulnerabilities without evidence. No High/Critical finding may be waived to enable a side-effecting capability. Accepted residuals identify decision owner, rationale, compensating controls, scope, and expiry/revisit trigger.

## PR acceptance checklist
- [ ] Scope, non-goals, and governing decisions identified.
- [ ] Threat model and trust boundaries reviewed.
- [ ] Security invariants and fail-closed behavior documented.
- [ ] Positive, negative, boundary, and regression tests added.
- [ ] Denied paths proven not to reach side-effect handlers.
- [ ] Relevant lint/tests/build/security checks completed successfully.
- [ ] Platform-specific behavior has matching CI evidence or is NOT VERIFIED.
- [ ] Full diff and changed-file list reviewed.
- [ ] No secret, unsafe execution path, arbitrary permission, or unauthorized data flow introduced.
- [ ] Independent review findings resolved or dispositioned.
- [ ] Capability remains disabled unless separately approved.
- [ ] Product Owner merge approval obtained for runtime changes.

## AI coding-agent contract
AI agents MUST read AGENTS.md/provider entry points and this standard; inspect actual source/tests; never invent paths, APIs, commands, or CI results; threat-model and test security-sensitive work before coding; make minimal task-scoped changes; never weaken tests/remove guards/skip checks to make CI green; never claim unperformed tests/reviews/merges; stop as BLOCKED if security cannot be implemented or verified; and keep Product Owner authorization, independent review, CI evidence, and merge approval as separate gates.

## Change control
This policy does not replace phase documents or Product Owner decisions. If it conflicts with an approved decision, stop and reconcile. Changes require a reviewed PR and Product Owner approval.
