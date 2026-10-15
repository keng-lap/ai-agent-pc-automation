# Phase 1 — Local Development Environment

## Status

**In Progress**

The development environment is built and verified in a Linux sandbox. Verification on the project owner's Windows 11 machine and the owner's review are still open. See Section 7.

## Objective

Provide a runnable local development environment for the project: tool choices, local workflow, basic application structure, environment variables and development scripts.

No Agent, tool, or PC-automation functionality is implemented in this phase.

---

# 1. Decisions

Approved by the project owner on 2026-10-15.

| Area | Decision |
|------|----------|
| Frontend | Angular, TypeScript |
| Backend | Python, FastAPI (served by uvicorn) |
| Languages | Two: TypeScript (frontend) and Python (backend) |
| Package managers | npm (frontend), pip with a virtual environment (backend) |
| Scripts | PowerShell (target: Windows 11) |
| Security | Proposal P-SEC-1 (`docs/PROPOSALS.md`) is approved for Phase 1 only: backend and dev server bind to `127.0.0.1` only |

No other proposal in `docs/PROPOSALS.md` is approved or implemented.

---

# 2. Prerequisites (Windows 11)

- Git
- Python 3.11 or newer, on PATH
- Node.js that satisfies the Angular CLI requirement: `^22.22.3`, `^24.15.0` or `>=26.0.0` (this is declared in `src/frontend/package.json` as `engines`)
- npm (ships with Node.js)
- PowerShell 5.1 (built into Windows 11) or PowerShell 7

`scripts/setup.ps1` checks these versions and stops with a clear message if one is not met.

---

# 3. Repository Layout

```text
.env.example          Environment variable template (copied to .env, which is git-ignored)
scripts/              PowerShell development scripts
src/backend/          Python FastAPI application (package: agent_backend)
src/frontend/         Angular application
tests/backend/        Backend tests (pytest)
```

Frontend unit tests live next to the Angular code (`src/frontend/src/**/*.spec.ts`), following Angular CLI convention.

---

# 4. Local Workflow

Run from the repository root in PowerShell.

| Command | What it does |
|---------|--------------|
| `scripts\setup.ps1` | Checks tools, creates `.env` from `.env.example`, creates `.venv`, installs backend and frontend dependencies. Safe to run again. |
| `scripts\dev.ps1` | Starts backend and frontend together. Ctrl+C stops both. |
| `scripts\test.ps1` | Runs backend pytest and ruff, then the Angular unit tests. |

Default addresses (both loopback only):

- Backend health check: `http://127.0.0.1:8000/health`
- Frontend: `http://127.0.0.1:4200/`

## Environment variables

Defined in `.env.example`. The real `.env` is never committed. Do not put secrets in `.env.example`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `development` | Environment name. Backend auto-reload is on in `development`. |
| `BACKEND_HOST` | `127.0.0.1` | Must be a loopback address. Other values stop the backend at startup. |
| `BACKEND_PORT` | `8000` | Backend port. |
| `FRONTEND_PORT` | `4200` | Frontend dev server port. |
| `LOG_LEVEL` | `info` | Backend log level. |

---

# 5. Scope Boundaries

Not part of Phase 1 and not implemented:

- Any AI Agent logic, AI model or provider, or API keys
- Any tool or PC-automation capability
- Any user interface beyond a placeholder page
- Frontend-to-backend communication (Phase 2)
- Authentication, CORS, Origin/Host checks, CSRF, permission or confirmation (proposals in `docs/PROPOSALS.md`, not approved)

The backend has one endpoint, `GET /health`. The frontend is a single placeholder page.

---

# 6. Verification Record

Verified on 2026-10-15 in a Linux sandbox (not the owner's machine):

- Python 3.12.3, Node.js 24.22.0, npm 10.9.7, PowerShell 7.6.7 (Linux)
- Angular CLI 22.2.2, Angular 22.2.3, FastAPI 0.143.1, uvicorn 0.54.0
- Backend: 14 pytest tests passed, ruff check and format check passed
- Frontend: 2 unit tests passed, production build succeeded
- `scripts/setup.ps1` from a clean `.venv` and clean `node_modules`: succeeded
- `scripts/test.ps1`: all checks passed
- `scripts/dev.ps1`: backend `/health` returned 200 and the frontend page was served
- Listening sockets were `127.0.0.1:8000` and `127.0.0.1:4200` only. Requests to the machine's non-loopback address on both ports failed.
- `BACKEND_HOST=0.0.0.0` is rejected by the backend, and `dev.ps1` stops

Not verified:

- Windows 11 and Windows PowerShell 5.1 (the scripts have a Windows branch for starting and stopping processes that has not been run)
- Python 3.11 and Node.js 22.x
- Process shutdown on Linux leaves the Angular child process running, because the script uses a Windows-only process-tree kill. This does not affect the Windows target but should be confirmed there.

---

# 7. Definition of Done

- [x] Programming languages and frameworks selected by the project owner
- [x] Local development workflow defined (Section 4)
- [x] Basic application structure created (backend and frontend)
- [x] Environment variables configured (`.env.example`)
- [x] Development scripts created (`scripts/`)
- [x] Backend and frontend tests pass in the sandbox (Section 6)
- [x] Documentation updated (`README.md`, `docs/PROJECT.md`, `docs/ROADMAP.md`, this file)
- [ ] `scripts\setup.ps1`, `scripts\dev.ps1` and `scripts\test.ps1` verified on the project owner's Windows 11 machine
- [ ] Project owner review and approval
- [ ] Branch pushed to GitHub and verified
- [ ] Merged into `main` after project owner approval
- [ ] GitHub repository verified after merge
- [ ] Project owner explicitly starts Phase 2

Phase 1 is not marked complete until every item above is checked.

---

# 8. Git

- Do not commit directly to `main`. Work on a branch, push it, and merge only after owner review.
- This phase was prepared on branch `feat/phase-1-dev-environment`.
