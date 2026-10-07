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

**Phase 0 — Project Foundation**

We are currently preparing the project structure, documentation, development rules, and Git workflow.

No real PC automation should be implemented during Phase 0.

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