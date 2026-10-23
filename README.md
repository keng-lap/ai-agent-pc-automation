# AI Agent PC Automation

Personal AI Agent for controlling and automating tasks on a local Windows PC.

## Project Goal

Build a personal AI Agent that receives commands from a local web application and can safely perform approved PC automation tasks.

Examples:

- Install software
- Configure applications
- Check system information
- Run approved scripts
- Manage files
- Execute predefined PC maintenance tasks

## Current Phase

**Phase 2 — Local Web Application**

Phase 0 (Project Foundation) and Phase 1 (Local Development Environment) are complete. Phase 2 adds a local web application with a chat interface. Its specification was approved by the Product Owner on 2026-10-20.

No Agent or PC-automation functionality is implemented yet. Do not implement future-phase features early.

**Status:** Phase 2 is complete (2026-10-23). T-202 (PR #13), T-203 (PR #15), T-205 (PR #16), and T-204 (PR #18) are merged into `main`; PR #19 records the Product Owner's report that MV-01 to MV-14 passed, and PR #20 makes backend tests independent of local `.env` ports. See `docs/PHASE-2-COMPLETION-REPORT.md`. Phase 3 has not started.

## Architecture

Initial architecture:

```text
User
  |
  v
Local Web App
  |
  v
AI Agent
  |
  v
Task / Tool Layer
  |
  v
Windows PC
```

## Important Principles

1. Safety first.
2. Never execute dangerous commands without explicit authorization.
3. Every automation capability must be traceable.
4. Keep the project modular.
5. Use Git for all project changes.
6. Claude must read the project documentation before starting work.
7. Do not skip phases.
8. Do not implement future-phase features early.

## Development

The project will be developed incrementally by phases.

See:

- `docs/PROJECT.md`
- `docs/ROADMAP.md`
- `docs/PHASE-0.md`
- `docs/PHASE-1.md`
- `docs/PHASE-2.md` (approved specification and completed Phase 2 record)
- `docs/PHASE-2-COMPLETION-REPORT.md` (Phase 2 closeout evidence)

Non-binding proposals awaiting owner approval (not requirements): `docs/PROPOSALS.md`

## Local Development

Requires Windows 11, Git, Python 3.11+, and Node.js `^22.22.3`, `^24.15.0` or `>=26.0.0` (details in `docs/PHASE-1.md`).

From the repository root in PowerShell:

```text
scripts\setup.ps1    install dependencies and create .env (once)
scripts\dev.ps1      run backend and frontend (Ctrl+C stops both)
scripts\test.ps1     run all tests
```

- Backend health check: `http://127.0.0.1:8000/health`
- Frontend: `http://127.0.0.1:4200/`

Both servers bind to `127.0.0.1` only.
