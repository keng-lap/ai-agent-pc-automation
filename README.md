# AI Agent PC Automation

Personal AI Agent for safely automating approved tasks on a local Windows 11 PC through a local web application.

## Current project status
**Phase 4 — Tool / Task System: CLOSED (Product Owner approval, 2026-11-02). Phase 5 — Safety and Permission System: P5-510/P5-511 complete; P5-512 authorized and in draft PR #63. Gemini text-chat MVP separately authorized and manually tested successfully by the Product Owner (2026-11-07).**

- Phase 0–3 are complete.
- Phase 4 implementation PRs #45–#47 are merged. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed. Verification commit: 8233af5.
- Phase 5 planning baseline: docs/PHASE-5.md. P5-510 and P5-511 are merged; P5-512 is a draft runtime PR awaiting CI and explicit PO review/merge approval. Later Phase 5 tasks require separate authorization. This does not authorize real PC execution.
- The Four-Agent workflow is coordinator-managed with four separated roles; it is not four autonomous LLM processes or a runtime orchestrator.
- Machine-changing tools remain mock/dry-run. Phase 5 does not enable real execution; Phase 6 and each capability require separate authorization.
- Gemini text-only chat is separately approved as T-601. The current message and up to 10 recent user/assistant pairs may be sent to Gemini; context and API key remain in backend process memory only. The Product Owner confirmed that a real API-key connection test and chat exchange passed on 2026-11-07. Tool/function calling and PC actions remain disabled.

## Project goal
Build a personal AI Agent that receives natural-language commands from a local web application, plans tasks, selects controlled tools, asks for confirmation where required, and reports results.

Examples of future capabilities include software installation, application configuration, system information, file management, and predefined maintenance tasks. These examples are not blanket authorization to implement or execute them.

## Architecture
User -> Local Web App (loopback) -> FastAPI Backend -> Gemini API (text chat only, when configured)\n                                              -> Agent Core / Controlled Tool Layer (dry-run only)

## Safety principles
1. No unrestricted PC control.
2. All automation passes through backend-controlled tool contracts, allowlists, and validation.
3. No raw model text may be executed as a command.
4. Machine-changing tools remain dry-run/mock until Phase 5 is complete and explicitly approved.
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
