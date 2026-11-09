# AI Agent PC Automation

Personal AI Agent for safely automating approved tasks on a local Windows 11 PC through a local web application.

## Current project status
**Phase 4 — Tool / Task System: CLOSED (Product Owner approval, 2026-11-02). Phase 5 — P5-510 through P5-515 are complete and P5-517 approval-gated P1 Dry Run is merged. P5-516 independent security review is complete (PR #107). F-516-02 runtime audit producers and F-516-03 plan-only legacy entry point are resolved in PRs #109 and #108. F-516-04 status documentation is being reconciled. F-516-01 Google OIDC + authenticator-app TOTP runtime integration is merged (PRs #114–#119); its setup-script fixes are merged (PRs #122–#127). F-516-01 remains OPEN pending independent A4 review and real local Google OIDC + Windows DPAPI/authenticator smoke tests. Phase 6 and real PC execution are not authorized. Gemini text-chat MVP remains separately authorized under T-601.**

- Phase 0–3 are complete.
- Phase 4 implementation PRs #45–#47 are merged. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed. Verification commit: 8233af5.
- Phase 5 baseline: docs/PHASE-5.md. P5-510 through P5-515 closeout is complete. P5-516 findings are recorded in docs/P5-516-INDEPENDENT-SECURITY-REVIEW.md. F-516-02 was addressed by connecting bounded in-memory audit producers (PR #109); F-516-03 was addressed by making the legacy agent entry point plan-only (PR #108). F-516-04 is this documentation reconciliation. F-516-01 implementation is merged, but remains open until independent A4 review and local Windows/Google OIDC/authenticator smoke tests are complete.
- The Four-Agent workflow is coordinator-managed with four separated roles; it is not four autonomous LLM processes or a runtime orchestrator.
- Machine-changing tools remain mock/dry-run. Phase 5 does not enable real execution; Phase 6 and each capability require separate authorization.
- Gemini text-only chat is separately approved as T-601. The current message and up to 10 recent user/assistant pairs may be sent to Gemini; context and API key remain in backend process memory only. The Product Owner confirmed that a real API-key connection test and chat exchange passed on 2026-11-07. Tool/function calling and PC actions remain disabled.

## Project goal
Build a personal AI Agent that receives natural-language commands from a local web application, plans tasks, selects controlled tools, asks for confirmation where required, and reports results.

Examples of future capabilities include software installation, application configuration, system information, file management, and predefined maintenance tasks. These examples are not blanket authorization to implement or execute them.

## Architecture
User -> Local Web App (loopback) -> FastAPI Backend -> Gemini API (text chat only, when configured)
                                              -> Agent Core / Controlled Tool Layer (dry-run only)

## Safety principles
1. No unrestricted PC control.
2. All automation passes through backend-controlled tool contracts, allowlists, and validation.
3. No raw model text may be executed as a command.
4. Machine-changing tools remain mock/dry-run only. Phase 6 and each real machine-changing capability require separate authorization.
5. Preserve loopback binding and local API authorization.
6. No provider integration, credentials, or external data transfer without explicit approval.
7. Do not persist chat messages/history or task history unless a future decision explicitly authorizes it.
8. Use Git branches and reviewable changes; code/runtime PRs require Product Owner merge approval.
9. Documentation/planning may proceed when consistent with approved scope and decisions.

## Development
Windows 11 requirements and commands are documented in docs/PHASE-1.md.

From the repository root in PowerShell:
- scripts\setup.ps1
- scripts\dev.ps1
- scripts\test.ps1

Both backend and frontend bind to loopback. See docs/PROJECT.md, docs/ROADMAP.md, and the active phase document.
