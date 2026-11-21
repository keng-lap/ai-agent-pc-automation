# AI Agent PC Automation

Personal AI Agent for safely automating approved tasks on a local Windows 11 PC through a local web application.

## Current project status
**Phase 4 — CLOSED (Product Owner approval, 2026-11-02). Phase 5 — CLOSED (Product Owner approval, 2026-11-09; closeout recorded in `docs/P5-519-PHASE-5-CLOSEOUT-REPORT.md`). P5-510–P5-515 are complete; P5-516 review findings are documented; F-516-02 and F-516-03 fixes are merged; F-516-01 Google OIDC + authenticator-app TOTP implementation is merged, while its targeted post-implementation A4 review is explicitly accepted as a residual verification gap by the Product Owner, not claimed as passed. P5-517 approval-gated P1 Dry Run and P5-518 visual workflow are merged (#99 and #130). Phase 6 planning is AUTHORIZED by the Product Owner on 2026-11-09. On 2026-11-21 the Product Owner separately authorized bounded implementation of real local `software.install` through WinGet, exact-action TOTP approval, a durable queue, and a contained Windows worker (P6-609-C / PR #170). This does not authorize a live install on the user's PC: Publisher Trust and Windows acceptance must pass, and the exact package still requires explicit approval. All other machine-changing capabilities remain separately gated. Gemini text-chat MVP remains separately authorized under T-601.**

- Phase 0–3 are complete.
- Phase 4 implementation PRs #45–#47 are merged. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed. Verification commit: 8233af5.
- Phase 5 closeout: `docs/P5-519-PHASE-5-CLOSEOUT-REPORT.md`. P5-515 closeout is complete with 33 Covered / 2 Partial. P5-516 findings remain documented; F-516-02 (#109) and F-516-03 (#108) are resolved. F-516-01 Google OIDC + authenticator-app TOTP implementation is merged (#114–#119), but the targeted post-implementation A4 review remains unperformed and is explicitly accepted as a residual verification gap for Phase 5 closeout by the Product Owner on 2026-11-09. This is not an A4 pass or a claim that the finding is technically eliminated. P5-517 (#99) and P5-518 (#130) are merged. P6-609-C / PR #170 implements the separately authorized real WinGet path for `software.install`; it remains Draft, unmerged, and blocked from live execution until the publisher certificate pin and Windows acceptance are complete. Other capabilities remain separately gated.
- The Four-Agent workflow is coordinator-managed with four separated roles; it is not four autonomous LLM processes or a runtime orchestrator.
- The `software.install` real WinGet path is being implemented under P6-609-C with exact Package ID/version binding, Publisher Trust, TOTP, durable queueing, process containment, and post-install verification. The legacy generic Dry Run approval path is blocked for `software.install`. `software.remove` and all other machine-changing tools remain preview-only. No live installation has been performed.
- Gemini text-only chat is separately approved as T-601. The current message and up to 10 recent user/assistant pairs may be sent to Gemini; context and API key remain in backend process memory only. The Product Owner confirmed that a real API-key connection test and chat exchange passed on 2026-11-07. Tool/function calling and PC actions remain disabled.

## Project goal
Build a personal AI Agent that receives natural-language commands from a local web application, plans tasks, selects controlled tools, asks for confirmation where required, and reports results.

Examples of future capabilities include software installation, application configuration, system information, file management, and predefined maintenance tasks. These examples are not blanket authorization to implement or execute them.

## Architecture
User -> Local Web App (loopback) -> FastAPI Backend -> Gemini API (text chat only, when configured)
                                              -> Agent Core / Controlled Tool Layer (preview tools + capability-gated local WinGet execution)

## Safety principles
1. No unrestricted PC control.
2. All automation passes through backend-controlled tool contracts, allowlists, and validation.
3. No raw model text may be executed as a command.
4. `software.install` is authorized for bounded local WinGet implementation under P6-609-C, but remains disabled until Publisher Trust and Windows acceptance pass. Other machine-changing capabilities remain mock/preview-only and require separate explicit authorization.
5. Preserve loopback binding and local API authorization.
6. No provider integration, credentials, or external data transfer without separate explicit approval. The Gemini text-chat flow is approved only within T-601's documented limits; this does not authorize Gemini tool/function calling or PC actions.
7. Do not persist chat messages/history or task history unless a future decision explicitly authorizes it.
8. Use Git branches and reviewable changes; code/runtime PRs require Product Owner merge approval.
9. Documentation/planning may proceed when consistent with approved scope and decisions.

## Development
Windows 11 requirements and commands are documented in docs/PHASE-1.md.

From the repository root in PowerShell:
- scripts\setup.ps1
- scripts\dev.ps1
- scripts\test.ps1

Both backend and frontend bind to loopback. See docs/PROJECT.md, docs/ROADMAP.md, and the active phase document (`docs/PHASE-6.md`).
