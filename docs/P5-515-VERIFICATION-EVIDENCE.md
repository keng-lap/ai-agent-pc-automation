# P5-515 — Verification Evidence

## Status

**In progress.** PR #66 is merged. GitHub Actions CI passed on the merge commit. This report records only facts available from the merged repository and GitHub Actions metadata; it does not claim full P5-515 or Phase 5 closeout.

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
