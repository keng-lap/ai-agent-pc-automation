# Phase 0 — Project Foundation

## Status

**In Progress**

Close-out work (directory structure, `.gitignore`, status reconciliation, recorded proposals) is prepared on a separate branch and awaits project owner review and merge. Remaining items are listed in Section 7.

## Objective

Prepare the project foundation so that another developer or AI coding agent can understand the project and continue development without needing the original conversation.

---

# 1. Phase 0 Goals

Phase 0 must establish:

- Project identity
- Project purpose
- Initial architecture
- Development rules
- Safety principles
- Git workflow
- Claude working rules
- Future development roadmap

No production Agent functionality should be implemented during this phase.

---

# 2. Required Files

The following files must exist:

```text
README.md
docs/
├── PROJECT.md
├── ROADMAP.md
└── PHASE-0.md
```

The project should also contain:

```text
src/
tests/
scripts/
.gitignore
```

These directories may remain empty during Phase 0. Because Git does not track empty directories, each contains a `.gitkeep` placeholder file.

Additional file (not required by Phase 0): `docs/PROPOSALS.md` records proposals that are pending project owner approval. It is not a source of truth.

---

# 3. Git Requirements

The project must use Git from the beginning.

Initial workflow:

```text
Create project
    ↓
Create documentation
    ↓
Review files
    ↓
git status
    ↓
git add
    ↓
git commit
    ↓
git push
    ↓
Verify GitHub
```

The first commit should represent the completed Phase 0 foundation.

Recommended commit message:

```text
chore: initialize project foundation
```

## Branch rule for all later changes

Project owner directive (2026-10-09):

- After the initial commit, do not commit directly to `main`.
- Make changes on a dedicated branch and push that branch.
- Merge into `main` only after the project owner has reviewed and approved the changes.
- A general branch naming convention is not defined yet (see `docs/PROPOSALS.md`).

---

# 4. Claude Working Rules

When Claude begins working on this project, Claude must first read:

```text
README.md
docs/PROJECT.md
docs/ROADMAP.md
docs/PHASE-0.md
```

Claude must then report:

1. What the project is.
2. What the current phase is.
3. What has already been completed.
4. What the next task should be.
5. Any assumptions or uncertainties.

Claude must NOT immediately start writing application code.

---

# 5. Phase Boundary

Phase 0 must NOT implement:

- AI model integration
- Chat UI
- PC automation
- Software installation
- Command execution
- File deletion
- Windows administration
- Autonomous computer control

Those features belong to later phases.

---

# 6. Safety Principle

The Agent will eventually control a real Windows computer.

Therefore safety is a core architectural requirement.

The future system must use controlled tools rather than giving the AI unrestricted operating-system access.

Potentially dangerous operations must require appropriate validation and, when necessary, explicit user confirmation.

Examples:

```text
Delete files
Install software
Uninstall software
Run administrator commands
Modify system configuration
Modify security settings
Modify network settings
```

---

# 7. Definition of Done

Phase 0 is complete when:

- [x] Git repository exists
- [x] Project directory exists
- [x] README.md exists
- [x] PROJECT.md exists
- [x] ROADMAP.md exists
- [x] PHASE-0.md exists
- [x] src/ exists (tracked via `.gitkeep`)
- [x] tests/ exists (tracked via `.gitkeep`)
- [x] scripts/ exists (tracked via `.gitkeep`)
- [x] .gitignore exists (populated; tested with `git check-ignore`)
- [x] Documentation consistency check completed by Claude (2026-10-09)
- [ ] Documentation reviewed and approved by the project owner
- [x] Git commit created (initial commit `2e0c28f`, verified with `git log`)
- [x] GitHub push completed (initial commit `2e0c28f` verified present on `origin/main` from a fresh clone)
- [ ] Close-out branch pushed to GitHub and verified
- [ ] Close-out changes merged into `main` after project owner approval
- [ ] GitHub repository verified after merge (`main` up to date with `origin/main`, working tree clean)

Phase 0 is not marked complete until every item above is checked.

---

# 8. Expected Git Status

Before the first commit, the working tree should contain the Phase 0 files.

After committing and pushing, the expected state is:

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

---

# 9. Phase 0 Completion Report

When Phase 0 is complete, report:

```text
PHASE 0 COMPLETE

Project:
AI Agent PC Automation

Completed:
- Project structure
- Documentation
- Architecture definition
- Roadmap
- Safety principles
- Git initialization

Git:
- Initial commit created
- Changes pushed to GitHub

Next Phase:
Phase 1 — Local Development Environment
```

---

# 10. Handoff to Claude

After Phase 0 is committed and pushed, Claude can be given the following instruction:

```text
You are joining an existing software project.

Before doing anything:

1. Read README.md.
2. Read docs/PROJECT.md.
3. Read docs/ROADMAP.md.
4. Read docs/PHASE-0.md.
5. Inspect the repository structure.
6. Check the current Git status.
7. Identify the current project phase.
8. Summarize your understanding.

Do not write implementation code yet.

Wait for the project owner to explicitly start the next phase.

The project owner will give you tasks phase by phase.

Do not skip phases.
Do not invent requirements.
Do not implement future-phase functionality early.
```

This instruction is the initial Claude handoff protocol.