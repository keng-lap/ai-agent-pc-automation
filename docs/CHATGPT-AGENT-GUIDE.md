# ChatGPT Agent Guide

## Purpose

This guide explains how ChatGPT should work on this repository when the user asks ChatGPT to act as the project coordinator or coding assistant. It complements `GEMINI.md`; it does not replace the repository's source of truth or grant additional permissions.

## Important capability boundary

- ChatGPT does **not** automatically discover or activate files in `.agents/skills/` merely because they exist in the repository.
- When the GitHub connection is available, ChatGPT should read `GEMINI.md`, this guide, relevant project/phase/decision documents, and only the skill files needed for the current task.
- Treat repository `SKILL.md` and reference files as procedures to consult, not as executable tools or proof that a host supports native Skill activation.
- If repository access is unavailable, state the limitation and request only the specific missing evidence needed. Do not pretend that files were read.
- ChatGPT cannot run PowerShell or inspect the user's Windows machine through GitHub access. Give concise commands for the user to run locally and distinguish user-reported results from independently verified results.
- Do not use Gemini CLI slash commands such as `/skills list` or `/skills reload` in ChatGPT. Those commands, if supported, belong to the relevant CLI host and its terminal session.

## Session-start procedure

1. Confirm the repository and current `main` commit using the connected GitHub source.
2. Read `GEMINI.md` and this guide.
3. Read `docs/PROJECT.md`, `docs/ROADMAP.md`, the active phase/task document, and relevant approved decision records.
4. Inspect relevant open/merged PRs and CI evidence before stating status.
5. Consult only the relevant skill files under `.agents/skills/`:
   - `project-context` for status, phase, scope, and handoff
   - `git-workflow` for branches, diffs, commits, and PRs
   - `testing-qa` for test selection and evidence
   - `windows-safety` for machine-action and approval boundaries
   - `debugging-token` for diagnosis and concise reporting
   - `documentation-decisions` for documentation and decision records
   - `frontend-design` for Angular UX/UI, design system, workflow canvas, accessibility, and frontend performance; also read only the relevant reference files in its references folder
6. Report a checkpoint in no more than five concise Thai bullets, then continue the next already-authorized task.

## Work and approval rules

- Follow all safety, phase, privacy, and approval rules in `GEMINI.md`, `docs/PROJECT.md`, `docs/ROADMAP.md`, and current approved decisions.
- Never infer approval from silence, a preview, or a successful test.
- Documentation-only changes may be made and merged when they are consistent with approved decisions and do not change requirements, scope, security, or runtime behavior.
- Runtime/code changes require a bounded task, applicable tests, review, and explicit Product Owner authorization/merge approval under the active phase rules.
- Never perform real Windows machine-changing actions. Installation/removal, file changes, administrator commands, process control, and system/network/security changes remain blocked unless separately authorized under the approved phase and capability gates.
- Never execute arbitrary model text, shell/PowerShell/CMD, scripts, dynamic imports, or unapproved tools.
- Preserve local-first/loopback boundaries. Do not introduce public remote access, mobile remote PC control, new providers, external data flows, credentials, or retention behavior without explicit approval.
- Phase 6 planning authorization does not grant individual real PC-changing capabilities. Follow the active Phase 6 gates and capability-specific approvals.

## Reporting standard

Use four distinct labels where relevant: **merged**, **CI-verified**, **locally verified**, and **user-reported**. Never claim a check passed without evidence. Report only what changed, what was verified, remaining gaps, and the next bounded step.
