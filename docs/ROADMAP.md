# Project Roadmap

## Overview

The project will be developed incrementally.

Each phase must be completed, tested, documented, and committed to Git before moving to the next phase.

---

# Phase 0 — Foundation

## Goal

Prepare the project foundation.

## Tasks

- Create Git repository
- Create project structure
- Create project documentation
- Define architecture
- Define development rules
- Define safety principles
- Define Claude working rules

## Deliverables

- README.md
- PROJECT.md
- ROADMAP.md
- PHASE-0.md
- Git repository

## Status

**Complete** — see `docs/PHASE-0.md`, Section 7.

---

# Phase 1 — Local Development Environment

## Goal

Prepare the development environment.

## Tasks

- Select programming language
- Select backend framework
- Select frontend framework
- Define local development workflow
- Create basic application structure
- Configure environment variables
- Create development scripts

## Deliverables

A runnable local development environment.

## Status

**Complete** — see `docs/PHASE-1.md`, Section 7.

---

# Phase 2 — Local Web Application

## Goal

Create the user interface for communicating with the Agent.

## Tasks

- Build local web application
- Create chat interface
- Send user commands to backend
- Display Agent responses
- Add basic error handling

## Deliverables

User can open a local web application and communicate with the Agent.

## Status

**Complete (2026-10-23)** — T-202 (PR #13), T-203 (PR #15), T-205 (PR #16), and T-204 (PR #18) are merged. The Product Owner reported MV-01 to MV-14 passed (PR #19). Final test and task evidence: `docs/PHASE-2-COMPLETION-REPORT.md`.

---

# Phase 3 — Agent Core

## Goal

Create the AI Agent core.

## Tasks

- Receive user command
- Analyze intent
- Create task plan
- Select appropriate tool
- Execute controlled tool
- Return result
- Handle errors

## Deliverables

A basic working AI Agent.

## Safety Constraint (P-ORDER-1, option A)

Product Owner decision (2026-10-19): the phase order does not change. Tools that can modify the machine are dry-run or mock only until the Safety and Permission System (Phase 5) is implemented and approved. See `docs/PROPOSALS.md`.

## Status

**Implementation and T-306/T-307 verification gates complete; Phase 3 closeout review pending.** T-301 through T-307 are merged (PRs #22–#27 and #30). Windows 11 verification includes backend 100 tests, Ruff, frontend 21 tests, production build, proxy authentication, production bundle token scan, and duplicate-token rejection. The final `scripts/test.ps1` rerun after T-307 passed. See `docs/T-306-REPORT.md` and `docs/PHASE-3.md`. Phase 4 must not start until all Phase 3 acceptance criteria are reviewed and the Product Owner explicitly approves closeout. Live provider calls and real machine-changing actions remain disabled.

---

# Phase 4 — Tool / Task System

## Goal

Create a controlled system for PC automation.

## Initial Tools

Potential tools include:

- System information
- File operations
- Process management
- Application detection
- Software installation
- Software removal
- Command execution

Tools must have explicit permissions and validation.

## Deliverables

A controlled tool execution layer.

## Safety Constraint (P-ORDER-1, option A)

Product Owner decision (2026-10-19): the phase order does not change. Tools that can modify the machine are dry-run or mock only until the Safety and Permission System (Phase 5) is implemented and approved. See `docs/PROPOSALS.md`.

## Status

Not Started

---

# Phase 5 — Safety and Permission System

## Goal

Prevent unsafe or unintended actions.

## Tasks

- Classify commands by risk
- Add confirmation mechanism
- Add permission levels
- Validate tool parameters
- Add command restrictions
- Add audit logging

## Deliverables

A safer Agent capable of handling sensitive PC operations.

## Status

Not Started

---

# Phase 6 — Real PC Automation

## Goal

Enable useful real-world automation.

## Example Tasks

User:

> Install Chrome.

Agent:

```text
Task detected:
Install Google Chrome

Risk level:
Medium

Action:
Installation requires confirmation.

Proceed?
```

User:

> Yes.

Agent executes the approved installation and reports the result.

## Deliverables

Working PC automation workflows.

## Status

Not Started

---

# Phase 7 — Monitoring and Logging

## Goal

Make the system observable and debuggable.

## Tasks

- Agent logs
- Tool execution logs
- Error logs
- Task history
- Execution time
- Success/failure status

## Deliverables

A traceable Agent system.

## Status

Not Started

---

# Phase 8 — Reliability

## Goal

Improve reliability for everyday use.

## Tasks

- Retry handling
- Timeout handling
- Recovery mechanisms
- Better error messages
- Task state management
- Idempotent operations where possible

## Deliverables

A more reliable personal Agent.

## Status

Not Started

---

# Phase 9 — Advanced Agent

## Goal

Improve Agent intelligence and autonomy.

Potential features:

- Multi-step planning
- Task decomposition
- Tool selection
- Context memory
- User preferences
- Scheduled tasks
- Background tasks
- Task history

## Status

Not Started

---

# Phase 10 — Production-Ready Personal Agent

## Goal

Create a stable personal AI Agent suitable for daily use.

## Requirements

- Stable architecture
- Security controls
- Permission system
- Logging
- Error recovery
- Automated testing
- Documentation
- Backup/recovery strategy

## Status

Not Started

---

# Development Rule

Never skip a phase without explicitly reviewing the reason.

A phase is considered complete only when:

1. Implementation is complete.
2. Tests pass.
3. Documentation is updated.
4. Git changes are committed.
5. The project is pushed to GitHub.
6. The next phase is explicitly started.

---

# Current Position

```text
Phase 0  ██████████  Complete
Phase 1  ██████████  Complete
Phase 2  ██████████  Complete
Phase 3  ████████░░  Closeout review pending
Phase 4  ░░░░░░░░░░  Not Started
Phase 5  ░░░░░░░░░░  Not Started
Phase 6  ░░░░░░░░░░  Not Started
Phase 7  ░░░░░░░░░░  Not Started
Phase 8  ░░░░░░░░░░  Not Started
Phase 9  ░░░░░░░░░░  Not Started
Phase 10 ░░░░░░░░░░  Not Started
```
