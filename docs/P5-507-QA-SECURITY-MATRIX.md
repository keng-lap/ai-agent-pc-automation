# P5-507 — QA/Security Matrix and Acceptance Evidence Plan

## Status and boundary

**Approved verification baseline; execution is tracked by P5-515.** This matrix is reconciled to the binding P5-509 decisions. P5-515 executes only synthetic fixtures, fake clocks, in-process API tests, and spy handlers. It does not inspect the user's PC or enable any machine-changing operation.

All Phase 5 implementation and verification must remain mock/dry-run only. P2 inspection and P3 machine changes remain denied. The matrix is a test design, not evidence that any test has passed.

## 1. Verification principles

- Backend is the sole authority for risk, permission, policy, confirmation, and dispatch decisions.
- Fail closed: invalid, missing, stale, mismatched, replayed, revoked, or unavailable policy/authorization must never reach a handler.
- Test negative paths before positive paths.
- Use isolated unit/API tests and deterministic fixtures; never use the user's live PC as a test fixture.
- Use fake handlers that record invocation in memory and cannot perform OS, filesystem, process, registry, network, package-manager, installer, or system-setting operations.
- No provider, live model, credentials, external transfer, or live package/source lookup.
- A test passes only when its actual command, exit code, and relevant output are recorded. No inferred CI status.
- A4 reviews evidence and limitations; the Product Owner alone resolves open decisions and authorizes runtime work/merges.

## 2. Test environment constraints

Allowed:
- Unit tests for pure validation/policy/lifecycle functions.
- API tests with local test client and synthetic requests.
- Fake clock, deterministic random/ID fixtures where appropriate, fake in-memory event sink, and spy handlers.
- Frontend component/accessibility tests with mocked API responses.
- Static inspection of diffs and dependency graphs.

Prohibited:
- Real installation/removal, real OS commands, PowerShell/CMD/script/process creation.
- Reading or changing installed software, files, registry, processes, network settings, credentials, or machine inventory.
- Real package-manager or internet source checks.
- Provider integration, external telemetry, or sending user data outside loopback.
- Testing with actual secrets or personal data.

## 3. QA/security matrix

| ID | Area | Test scenario | Expected result / evidence |
|---|---|---|---|
| Q01 | Request schema | Missing required field | Reject before planner/handler |
| Q02 | Request schema | Unknown/extra field | Reject; no permissive coercion |
| Q03 | Request bounds | Body exceeds 16 KiB | Reject at HTTP boundary |
| Q04 | HTTP boundary | Missing/invalid/duplicate local token on /api | Reject; no downstream dispatch |
| Q05 | HTTP boundary | Disallowed Host or missing/invalid Origin on state change | Reject before route logic |
| Q06 | Content type | State-changing request is not JSON | Reject |
| Q07 | Catalog | Unknown tool/action ID | Deny; no dynamic lookup/import |
| Q08 | Catalog | Client attempts to supply handler/risk/permission | Reject extra/untrusted metadata |
| Q09 | Policy | Policy missing, duplicate, malformed, inconsistent | Startup/request fails closed; no handler |
| Q10 | Policy | Client/model claims low risk or permission | Ignore/reject claim; backend-derived decision prevails |
| Q11 | Policy | P2 inspection requested | Deny |
| Q12 | Policy | P3 install/remove execution requested | Deny; no execution handler exists |
| Q13 | Dispatch | Fixed handler identity or policy version changes after decision | Final guard denies |
| Q14 | Dispatch | Handler map missing or unexpected | Safe denial; no fallback |
| Q15 | Dry-run | Approved P1 catalog item | Fake/dry-run handler only; spy confirms no side effects |
| Q16 | Parameters | Invalid type, extra parameter, out-of-range value | Reject before handler |
| Q17 | P1 lifecycle | Attempt acknowledgement, approval, cancellation, or execute route | No such P1 state-transition endpoint exists; unknown routes return 404 |
| Q18 | Plan identity | Refine a plan with explicit answers | New immutable plan ID/digest; original plan remains unchanged |
| Q19 | Plan integrity | Tamper with stored plan digest | Reject and invalidate the affected reference; no dispatch |
| Q20 | Expiry | Read a plan at and after its 10-minute TTL boundary | Expired reference is rejected and then unavailable |
| Q21 | Restart / clock | New process store or backward clock movement | Old references are unavailable; clock rollback fails closed |
| Q22 | Digest binding | Change material fields, tool identity, or program order | Digest changes; equivalent content retains digest but receives a distinct opaque ID |
| Q23 | API response | Handler error or malformed result | Bounded safe error; no stack trace/secrets |
| Q24 | Audit | Event includes prompt/token/raw parameters | Schema rejects or redaction prevents persistence |
| Q25 | Audit | Event sink unavailable | No unsafe fallback; behavior follows approved failure policy |
| Q26 | Audit | Retention cap/expiry/restart | Selected PO-approved retention semantics enforced |
| Q27 | Privacy | Attempt external telemetry/provider call | No such integration/path exists |
| Q28 | Frontend | UI receives unknown status/missing field | Safe neutral error; never infer success |
| Q29 | Frontend | User changes language | Same plan/order/status; only labels change |
| Q30 | Frontend | Keyboard/screen-reader/mobile layout | Controls accessible; dry-run notice remains visible |
| Q31 | Frontend | Attempt to find execute/install/remove control | No such control or equivalent API path |
| Q32 | Regression | Existing loopback/token/Host/Origin/body limits | Controls remain effective |
| Q33 | Regression | Existing install/remove dry-run tools | Still mock-only; no machine side effect |
| Q34 | Failure handling | Planner/policy/handler throws | Safe bounded failure; no fallback or retry with broader capability |
| Q35 | Scope | Test attempts file/registry/process/network inspection | Test harness contains no such capability; prohibited |

## 4. Evidence required per test

For each executed test, record:
- Test ID and exact test name.
- Commit SHA and test environment/runtime version.
- Exact command invoked.
- Exit code and pass/fail result.
- Relevant concise output or assertion evidence.
- Whether test used a fake/spy and confirmation that no real side-effect capability was available.
- Known limitations or skipped conditions.

Do not record secrets, full prompts, personal data, full machine inventory, or raw environment dumps. Screenshots are optional and must be redacted. A summary such as "tests passed" without command/output evidence is insufficient.

## 5. Proposed test layers and sequencing

1. Pure schema and catalog tests.
2. Policy table validation and policy-decision unit tests.
3. Final pre-dispatch guard tests with spy handlers.
4. Confirmation lifecycle, digest binding, expiry, replay, cancellation, and concurrency tests.
5. API boundary/security middleware tests.
6. Audit schema, redaction, retention, and failure-policy tests after PO decisions.
7. Frontend rendering, localization, keyboard, screen-reader, and mobile tests.
8. End-to-end local test-client flow using only fake data and fake handlers.
9. Regression suite and A4 review of all diffs/evidence.

A layer cannot claim completion if a dependency or required PO decision is unresolved. Do not create tests that imply real execution is supported.

## 6. Release and merge gates

For every future runtime task:
- Separate bounded task and branch using `<type>/<task-id>-<short-name>`.
- Explicit PO authorization before runtime work begins.
- Tests must be targeted to the change and include negative/abuse cases.
- Review exact diff, changed paths, line endings, and `git diff --check`.
- A4 review must be independent of implementation.
- Explicit PO approval is required before merging runtime/code PRs.
- No CI pass may be claimed without visible successful checks/evidence.
- A merge does not grant P2/P3 permission or Phase 6 authority.

Documentation-only PRs may be merged under the user's standing permission after verifying that every changed path is under `docs/`.

## 7. Phase 5 acceptance evidence checklist

- [ ] Risk/permission policy is explicit and backend-owned.
- [ ] Policy startup validation and request-time decision fail closed.
- [ ] Final pre-dispatch guard is proven with spy-handler negative tests.
- [ ] No execution-capable handler is reachable in Phase 5.
- [ ] Confirmation binds exact immutable parameters and handles expiry/replay/cancel/concurrency.
- [ ] UX makes every proposed program and unknown explicit; no execution control exists.
- [ ] Audit/privacy behavior matches explicit PO retention decision.
- [ ] Existing HTTP/local-token protections are regression-tested.
- [ ] Frontend is accessible and bilingual behavior is verified.
- [ ] Test commands, outputs, exit codes, commit SHAs, and limitations are recorded.
- [ ] A4 independent review is complete.
- [ ] Product Owner explicitly approves Phase 5 closeout.

## 8. Open decisions and limitations

The matrix depends on PO decisions in P5-502 through P5-506, including risk/permission mapping, confirmation lifecycle, acknowledgement, retention, and UX/API shape. Test implementation must not hard-code unresolved proposal choices as if already approved.

This plan does not claim that any tests have run or passed. It does not authorize runtime implementation. No Phase 6 capability or real PC operation is authorized.



## 9. P5-515 execution evidence (merge commit)

The first bounded P5-515 test increment was merged in PR #66. The merge commit is `3d661d7e56c431722abf5dd3c0aae23e631c546e`. GitHub Actions CI run [42355435380](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42355435380) completed with conclusion `success`; its backend and frontend jobs both completed successfully.

The workflow's actual commands and configured environments are defined in `.github/workflows/ci.yml`:
- Backend tests: from `src/backend`, `python -m pytest ../../tests/backend` (Ubuntu runner, Python 3.12; CI step successful).
- Ruff: from `src/backend`, `ruff check agent_backend ../../tests/backend` (CI step successful).
- Frontend unit tests: from `src/frontend`, `npm test -- --watch=false` (Ubuntu runner, Node 24; CI step successful).
- Frontend build: from `src/frontend`, `npm run build` (CI step successful).

The available GitHub run/job metadata confirms successful step conclusions but does not expose raw stdout, exact pytest collection/pass count, or explicit process exit-code text. Those details are not asserted here. See the linked run for authoritative job status.

Existing backend tests provide deterministic fake-clock coverage for expiry and clock rollback, process-local store restart invalidation, plan digest binding/tamper detection, and audit sink capacity/restart/clear behavior. PR #66 adds synthetic HTTP-boundary and spy-handler regression cases. The suite uses in-process test clients, synthetic values, and dry-run handlers; it does not execute OS commands, installers, package managers, filesystem mutations, registry operations, or real PC changes.

P5-515 is **in progress**, not closed: merge-commit CI is green, but complete matrix-to-test traceability and A4 independent review/evidence closeout remain outstanding. P5-516 remains a separately gated independent review.
