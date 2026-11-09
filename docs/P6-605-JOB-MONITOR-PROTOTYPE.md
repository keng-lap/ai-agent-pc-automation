# P6-605 — Execution Nodes and Job Monitor UX Prototype

## Scope
Frontend-only, synthetic in-memory prototype extending the Angular Workflow Builder and adding a Job Monitor workspace.

## Workflow Builder additions
- Run Custom Script: PowerShell, BAT/CMD, Python, and Node.js visual concept.
- Install Software: package selection and publisher/version/source review concept.
- Batch Install: multi-package plan concept.

These are design-time node types only. They do not dispatch commands, install packages, or execute scripts. Future side-effecting implementation requires strict typed schemas, immutable artifact/package identity, exact-action approval, timeout/cancellation, audit, least privilege, independent A4 review, tests, and explicit Product Owner enablement.

## Job Monitor
- Active Jobs and Run History tabs with search.
- Run details include Job Run ID, workflow label/version, progress, current node, per-node status/duration, and sanitized sample logs.
- All records are synthetic fixtures. No API, persistence, polling, real-time updates, or actual execution is connected.

## Safety
No backend or Workflow Engine changes; no live Windows inspection/mutation; no real logs, secrets, or script contents are read.
