# P5-515 — Verification Evidence

## Status

**In progress.** PRs #66, #73, #74, #75, and #77 are merged. GitHub Actions CI passed for the final PR heads of #73, #74, #75, and #77. The matrix is reconciled to 25 Covered / 10 Partial. This report records only facts available from merged repository content and GitHub Actions metadata; it does not claim full P5-515 or Phase 5 closeout.

## Source and CI identity

- Repository: `keng-lap/ai-agent-pc-automation`
- PR: [#66 — negative/abuse/regression coverage](https://github.com/keng-lap/ai-agent-pc-automation/pull/66)
- Merge commit: `3d661d7e56c431722abf5dd3c0aae23e631c546e`
- Workflow run: [CI #42355435380](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42355435380)
- Workflow conclusion: `success`
- Runner: GitHub-hosted `ubuntu-latest`
- Backend runtime: Python `3.12` (workflow configuration)
- Frontend runtime: Node.js `24` (workflow configuration)

## Actual CI commands and observed outcomes

Commands below are copied from `.github/workflows/ci.yml`. Working directories and configured runtime versions are shown as defined by the workflow.

| Area | Working directory | Command | Observed CI outcome |
|---|---|---|---|
| Backend tests | `src/backend` | `python -m pytest ../../tests/backend` | Step completed successfully |
| Ruff | `src/backend` | `ruff check agent_backend ../../tests/backend` | Step completed successfully |
| Frontend unit tests | `src/frontend` | `npm test -- --watch=false` | Step completed successfully |
| Frontend build | `src/frontend` | `npm run build` | Step completed successfully |

GitHub run metadata reports both jobs (`backend`, `frontend`) as `completed / success`. Available metadata does not include raw command stdout, exact pytest pass count, or explicit textual exit-code lines. Accordingly, this report records successful step conclusions and does not invent test counts or output excerpts. The workflow run and job pages are the authoritative CI evidence.

## Coverage present in the repository

- PR #66 adds synthetic API tests for missing/invalid local token, foreign/missing Origin, non-JSON content type, oversized request body, client-supplied authority/execution fields, absence of P1 acknowledgement/approval/cancel/execute routes, unknown plan references, denied-policy spy-handler non-invocation, and dry-run-only dispatch.
- Existing plan tests use an injected fake clock to cover TTL expiry and clock rollback, verify process-local store restart invalidation, bind material fields/tool identity/order into plan digests, and reject tampered plan digests.
- Existing audit tests cover strict allowlists, bounded capacity/oldest-first eviction, non-blocking optional diagnostics failure, and empty state after a new sink/process.

## Safety and limitations

- CI runs in GitHub-hosted Linux runners, using in-process test clients and synthetic fixtures.
- No Windows PC was used as a test fixture.
- No real OS command, process, installer, package manager, filesystem mutation, registry operation, network-setting change, or other machine-changing action was invoked.
- Current P1 remains plan/report and dry-run only. P2 inspection, P3 execution, Phase 6, and real PC actions remain unauthorized.
- P5-515 remains open until the QA matrix is fully reconciled to concrete test evidence and A4 independent review is completed.
- P5-516 is a separate independent-review task and has not started.


## Subsequent P5-515 increments

| PR | Scope | Merge commit | CI evidence |
|---|---|---|---|
| [#73](https://github.com/keng-lap/ai-agent-pc-automation/pull/73) | Static source-level audit for audit-sink transport/telemetry and bounded test-harness capability checks | `1a4f3a5024bb3ae7f4e9298284ef87d7bcee75a9` | [CI #42357992572](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42357992572) — successful |
| [#74](https://github.com/keng-lap/ai-agent-pc-automation/pull/74) | Q13 handler identity replacement guard and in-process spy-handler regression test | `eb6e858ad17a3224b3c1f75fcce80bc4e9bc8efe` | [CI #42358505456](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42358505456) — successful |
| [#75](https://github.com/keng-lap/ai-agent-pc-automation/pull/75) | Q23/Q34 API-boundary exception handling tests for planner, policy configuration, and tool handler | `2f512559bc32221b2559514e94b252036f2a0582` | [CI #42358957033](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42358957033) — successful |

PR #75 initially had a failed CI run (#42358655824): the default TestClient re-raised application exceptions instead of exposing the HTTP 500 response under test. The tests were corrected to use `raise_server_exceptions=False`, then the updated PR head passed backend tests, Ruff, frontend unit tests, and frontend build in CI #42358957033. The failed run is retained here for transparent audit history; it was not treated as a passing result.

The final successful PR #75 CI run reports:
- Backend tests: success
- Ruff: success
- Frontend unit tests: success
- Frontend build: success

No exact pytest pass count is asserted here because the authoritative evidence used for this update was the workflow/job conclusion metadata, not a separately preserved complete test summary.


- **PR #77:** [Q20 exact TTL boundary and Q23 malformed handler-result API-boundary tests](https://github.com/keng-lap/ai-agent-pc-automation/pull/77) — merge commit `2ad52b2045f0b7927935d44dae8161ce9369939b`; [CI #42359381703](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/42359381703) passed (backend, Ruff, frontend tests, frontend build).

PR #77 uses a fake clock to verify the plan is valid immediately before expiry and rejected at the exact expiry boundary. It also injects a synthetic malformed handler result through the in-process API client and verifies a generic HTTP 500 response with one handler invocation (no retry). No real host or machine-changing action is involved.

The updated source-level matrix records **24 Covered / 11 Partial / 0 Not covered or not evidenced**. Q20, Q23, and Q26 are now Covered; the remaining Partial rows are Q02, Q09–Q12, Q16, Q25–Q26, Q28, and Q30–Q31. This remains a traceability classification, not a P5-515 completion claim.

## Updated matrix classification

The merged source-level matrix now records:
- **Covered:** 24 items
- **Partial:** 11 items
- **Not covered / not evidenced:** 0 items

Q13 is Covered after the handler-identity replacement regression test. Q34 is Covered after direct synthetic planner, policy-configuration, and handler exception tests at the API boundary. Q23 is Covered after PR #77 added a malformed handler-result test through the API boundary. See [P5-515 Matrix-to-Test Traceability](P5-515-MATRIX-TRACEABILITY.md) for exact test names and limitations.

## A4 QA/security review

The focused A4 QA/security review of merged increments #66, #73, #74, #75, and #77 is recorded in [P5-515 A4 QA/Security Review](P5-515-A4-QA-SECURITY-REVIEW.md). It supports the Q13, Q20, Q23, Q26, and Q34 coverage updates; Q35 remains Partial because the capability audit is static and bounded. This review is not the separately gated P5-516 review and does not close P5-515.

## Reproducibility reference

The backend commands, from the workflow's working directory:

```bash
cd src/backend
python -m pytest ../../tests/backend
ruff check agent_backend ../../tests/backend
```

Frontend CI commands:

```bash
cd src/frontend
npm ci
npm test -- --watch=false
npm run build
```

These are documentation references only; the Product Owner does not need to run them on the Windows PC for this verification.


## Matrix-to-test traceability

A source-level Q01–Q35 mapping is maintained in [P5-515 Matrix-to-Test Traceability](P5-515-MATRIX-TRACEABILITY.md). It records exact backend/frontend test names and distinguishes Covered, Partial, and Not covered / Not evidenced. The mapping is not a new CI run and does not close P5-515; unresolved gaps and A4 review remain open.


## Q26 retention decision reconciliation

The approved P5-508 decision is audit option A: bounded ephemeral in-memory events cleared on restart. The implementation caps the sink at 500 events and evicts oldest-first. Existing tests cover the 500-event default, FIFO eviction, and an empty new sink. A time-based event TTL and durable audit storage are not part of the approved decision. Q26 is classified Covered on that basis; no retention behavior was added.
