# AI Agent PC Automation

Personal AI Agent for safely automating approved tasks on a local Windows 11 PC through a local web application.

## Current project status
**Phase 4 — Tool / Task System: CLOSED (Product Owner approval, 2026-11-02). Phase 5 — Safety and Permission System: planning authorized (2026-11-02).**

- Phase 0–3 are complete.
- Phase 4 implementation PRs #45–#47 are merged. Product Owner Windows 11 verification: 75 backend tests passed, Ruff passed, and 22 frontend tests passed. Verification commit: 8233af5.
- Phase 5 planning baseline: docs/PHASE-5.md. Runtime implementation is not yet authorized.
- The Four-Agent workflow is coordinator-managed with four separated roles; it is not four autonomous LLM processes or a runtime orchestrator.
- Machine-changing tools remain mock/dry-run. Phase 5 does not enable real execution; Phase 6 and each capability require separate authorization.
- No AI provider, provider credentials, live model calls, or external data transfer are approved.

## Project goal
Build a personal AI Agent that receives natural-language commands from a local web application, plans tasks, selects controlled tools, asks for confirmation where required, and reports results.

Examples of future capabilities include software installation, application configuration, system information, file management, and predefined maintenance tasks. These examples are not blanket authorization to implement or execute them.

## Architecture
User -> Local Web App (loopback) -> Agent Core -> Controlled Tool / Task Layer -> Windows PC (only explicitly approved capabilities)

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
