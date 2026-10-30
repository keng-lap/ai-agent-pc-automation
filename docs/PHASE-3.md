# Phase 3 — Agent Core

## Status

**T-301 through T-308 are merged (PRs #22–#27, #30, #35, and #36).** T-306 local API authorization is implemented and verified on the Product Owner's Windows 11 PC. T-307 duplicate-token automated regression coverage is merged, and the final test-script rerun passed: backend 100 tests, Ruff, and frontend 21 tests. See `docs/T-306-REPORT.md` for the evidence.

**Phase 3 closeout is not approved.** T-308 implementation PR #35 and its parser correction PR #36 are merged. The Product Owner's latest Windows 11 test-script run passed (100 backend tests, Ruff, 21 frontend tests). A4 must now independently reassess all Phase 3 acceptance criteria using the merged source and recorded evidence. See `docs/PHASE-3-QA-REVIEW.md` and `docs/T-308-REPORT.md`. Phase 4 must not start until the Product Owner explicitly approves Phase 3 closeout.

ChatGPT remains a deterministic local-preview identifier; no live provider is connected. Provider authorization, external data transfer, model choice, and real machine-changing actions remain unapproved.

## Goal

Turn a chat request into an understandable plan, select an allowed tool, execute it through a controlled interface, and report success or failure. Phase 3 builds the Agent core while keeping machine-changing tools in mock or dry-run mode.

## Approved constraints

- Preserve the phase order in `ROADMAP.md` (P-ORDER-1, option A).
- Bind local services to loopback only (P-SEC-1 / D-SEC-5).
- Tools that can modify the computer must use mock or dry-run behavior until Phase 5's Safety and Permission System is implemented and approved.
- Phase 2's decision D-SEC-1 requires a local-authorization decision before Phase 3 enables any Agent capability. Phase 3 must define and enforce that boundary before enabling Agent processing through the application.
- Never treat model output as authorization. The backend owns validation and enforcement.
- Keep deterministic behavior testable without contacting a live AI provider.

## In scope

1. Define the request, plan, tool-call, result, and error contracts.
2. Analyze a request and produce an end-to-end structured plan, including all relevant prerequisites, software/tools, dependencies, and source-backed action proposals—not just items explicitly named by the user.
3. Select tools only from a backend-controlled allowlist.
4. Execute read-only tools, if approved for the task, and mock/dry-run implementations for machine-changing tools.
5. Return a user-readable result and safe, non-sensitive errors.
6. Add deterministic tests for validation, planning, tool selection, execution boundaries, and failures.

## Out of scope

- Real execution of actions that change files, processes, applications, software, or system settings.
- Integrating a provider before official account authorization, privacy/data-flow, model/fallback, and secure token-storage decisions are approved. Never scrape provider website sessions or cookies.
- Implementing Phase 5's full permission, confirmation, and audit system early under another name.
- Making the Agent available to non-loopback clients.

## Decisions required before provider-backed Agent behavior

| Decision | Required answer |
|---|---|
| AI provider and model | Provider set and per-run UI selection approved: GPT, Claude, Gemini. Specific model, fallback behavior, and provider integration remain open. |
| Data handling | Whether user messages may leave the computer, what data may be sent, and required retention/privacy constraints. |
| Account authorization | The Product Owner prefers signing in with the selected provider account. Official flow availability and secure token storage must be decided for each provider; never scrape browser sessions. |
| Local authorization (D-SEC-1) | **Approved: option A — require a random per-installation local token for every `/api/*` request.** Store it only in ignored `.env`; the local Angular development proxy injects it server-side. The backend compares it in constant time. Missing, invalid, or duplicate tokens receive 401. `/health` remains available without a token. This is local API authorization, not AI-provider sign-in. |
| Phase 3 tool boundary | Which read-only tools, if any, are approved; all machine-changing tools remain mock/dry-run. |

Until official provider authorization, data handling, and token-storage decisions are recorded in approved phase documents, use only deterministic local/mock behavior and do not make external provider calls.

## Proposed task sequence

| Task | Deliverable | Gate |
|---|---|---|
| T-301 | Approve this Phase 3 scope and safety boundary. | Complete: approved and merged in PR #22. |
| T-302 | Define Agent request/response, plan, tool, result, and error contracts; propose local authorization behavior and record provider boundary. | Complete: approved and merged in PR #23. Provider and local authorization decisions remain open before provider-backed processing. |
| T-303 | Implement deterministic intent analysis and plan generation with validation and tests. | Complete: merged in PR #24; current limitation documented in `docs/PHASE-3-QA-REVIEW.md`. |
| T-304 | Implement allowlisted tool selection and mock/dry-run execution with boundary tests. | Complete: merged in PR #25; no machine-changing side effects. |
| T-305 | Connect the Agent Core to the chat endpoint and report results/errors. | Complete: merged in PR #26 (`4cc2a63`). Deterministic local preview only; no provider call. |
| T-306 | Enforce D-SEC-1 local authorization on Agent API requests; generate and inject the per-installation token; add negative tests and update setup guidance. | Complete: merged in PR #27 (`4e9ebe9`); Windows 11 verification recorded in `docs/T-306-REPORT.md`. |
| T-307 | Add automated regression coverage proving duplicate `X-Local-Agent-Token` headers are rejected. | Complete: merged in PR #30 (merge commit `7b12e92`); final Windows 11 test-script rerun passed. |
| T-308 | Add task-specific prerequisite items with reasons, dependency order, explicit knowledge states, and deterministic tests. | Complete: PR #35 merged; parser correction PR #36 merged; Windows 11 test script passed. Final A4 Phase 3 reassessment pending. |

Tasks should be delivered in separate reviewable branches/PRs using `<type>/<task-id>-<short-name>`. Do not begin a gated task until its stated prerequisite is merged and any required decision is recorded.

## Acceptance criteria for Phase 3

- A request is validated and converted into an end-to-end plan that identifies relevant prerequisites and explains why each is needed.
- Tool selection is constrained to a backend allowlist and invalid/unknown tools are rejected safely.
- AI-proposed commands are validated against backend-owned tools and parameters; raw model text is never passed directly to a shell. Sensitive actions require approval of the exact action.
- Machine-changing tools cannot cause real side effects; tests demonstrate mock/dry-run behavior.
- The backend enforces the approved local-authorization boundary before processing Agent capabilities.
- Success and failure responses are predictable, useful, and do not expose secrets or internal tracebacks.
- Deterministic tests cover request validation, planning, tool selection, safety boundaries, and error handling.
- Documentation records provider/data-flow decisions and the final behavior; all changes are merged to GitHub before Phase 4 starts.

## Verification

- Windows 11 setup/startup, final backend tests (100), Ruff, frontend tests (21), production build, direct API authorization, frontend proxy, production bundle token scan, and duplicate-token manual rejection passed.
- T-307 automated duplicate-token regression test is merged in PR #30. The complete test script was rerun afterward and passed.
- GitHub Actions checks on the T-307 PR head completed successfully for CodeQL, Python analysis, and JavaScript/TypeScript analysis.
- Exact local evidence is recorded in `docs/T-306-REPORT.md`.
- A4's MA-005 review found acceptance criterion 1 not met; see `docs/PHASE-3-QA-REVIEW.md`. T-308 is merged in PRs #35 and #36. The latest Product Owner Windows 11 test-script run passed (100 backend tests, Ruff, 21 frontend tests). A4's independent final acceptance reassessment remains pending.
- Phase 3 must not be marked closed and Phase 4 must not start until the planner gap is resolved, all acceptance criteria are reviewed, closeout documentation is approved, and the Product Owner explicitly approves the transition.

## References

- `docs/ROADMAP.md` — Phase 3 scope and P-ORDER-1 constraint.
- `docs/PROPOSALS.md` — P-SEC-1, P-SEC-2, P-SEC-3, P-SEC-4, P-ORDER-1, and the open AI provider item.
- `docs/PHASE-2.md` — approved Phase 2 decisions, including D-SEC-1.
- `docs/PHASE-3-QA-REVIEW.md` — MA-005 A4 acceptance review.
