# Project Definition

## 1. Project Name

AI Agent PC Automation

## 2. Purpose

This project aims to build a personal AI Agent that can receive commands from a local web application and safely perform approved automation tasks on a Windows PC.

The system should eventually allow a user to communicate with the AI Agent using natural language.

Example:

> Install Google Chrome.

The Agent should understand the request, determine the required action, ask for confirmation when necessary, execute the task through a controlled tool layer, and report the result.

## 3. Target Environment

Initial target environment:

- Operating System: Windows 11
- Local machine
- Local Web Application
- Git / GitHub
- AI Agent
- Claude will participate in development
- Programming language and framework will be selected during the appropriate project phase

## 4. Initial Architecture

```text
+----------------+
|      User      |
+-------+--------+
        |
        v
+----------------+
|  Local Web App |
+-------+--------+
        |
        v
+----------------+
|    AI Agent    |
+-------+--------+
        |
        v
+----------------+
|  Tool / Task   |
|     Layer      |
+-------+--------+
        |
        v
+----------------+
|  Windows PC    |
+----------------+
```

## 5. Core Requirements

The future system should be able to:

1. Receive commands from the user.
2. Understand the user's intent.
3. Decide what task needs to be performed.
4. Use controlled tools to perform the task.
5. Request confirmation for sensitive operations.
6. Report success or failure.
7. Keep logs of important actions.
8. Prevent unauthorized or dangerous operations.

## 6. Safety Requirements

The Agent must NOT have unrestricted control of the computer.

All PC automation should go through a controlled tool layer.

Examples of potentially sensitive operations:

- Installing software
- Uninstalling software
- Deleting files
- Modifying system settings
- Running administrator commands
- Changing network configuration
- Modifying security settings

Sensitive operations must require explicit user approval unless a future phase defines a safe automated policy.

## 7. Development Philosophy

The project will be developed incrementally.

Each phase must:

- Have a clear objective.
- Have defined deliverables.
- Be tested before moving forward.
- Be committed to Git.
- Be documented.
- Not implement features belonging to future phases.

## 8. Role of Claude

Claude will act as a development assistant/engineering agent.

Claude must:

1. Read the project documentation before starting work.
2. Understand the current phase.
3. Follow the project architecture.
4. Avoid making assumptions about future phases.
5. Explain significant architectural decisions.
6. Create tests where appropriate.
7. Update documentation when required.
8. Use Git properly.
9. Never silently change project requirements.

## 9. Source of Truth

The following files are the primary project documentation:

```text
README.md
docs/PROJECT.md
docs/ROADMAP.md
docs/PHASE-0.md
```

If there is a conflict between implementation assumptions and these documents, stop and clarify the conflict before implementing major changes.

`docs/PROPOSALS.md` contains proposals that are pending project owner approval. It is not a source of truth and its contents are not requirements.

## 10. Current Status

Current phase:

**Phase 0 — Project Foundation**

Status:

**In Progress**

Phase 0 deliverables, the required directory structure (`src/`, `tests/`, `scripts/`) and `.gitignore` are in place. Remaining: project owner review, and merge of the close-out changes into `main`. See `docs/PHASE-0.md`, Section 7.

No production AI Agent functionality has been implemented yet.