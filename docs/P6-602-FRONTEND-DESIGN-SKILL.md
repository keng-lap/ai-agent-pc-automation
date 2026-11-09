# P6-602 — Frontend Design Skill

## Status
**Documentation implementation prepared; Product Owner review and PR merge pending.**

## Objective
Create a repository-specific frontend design skill that raises the quality bar for all application UI, with particular attention to the planned Visual Workflow Builder. The standard covers visual design, Thai-first usability, Angular compatibility, accessibility, interaction quality, performance measurement, and safety boundaries.

## Scope delivered
- Add .agents/skills/frontend-design/SKILL.md.
- Add focused references for the shared design system, workflow canvas, frontend performance, and UX quality checklist.
- Register the skill in docs/AGENT-SKILLS.md.
- Teach Gemini repository instructions to load the skill for frontend tasks.
- Teach ChatGPT repository guidance to retrieve the skill and relevant references explicitly.

## Product decisions captured
- The existing application frontend is Angular; React/React Flow is not assumed or selected.
- The Workflow Builder is an editor for a Job's versioned Workflow Definition. It is not a Node and does not execute jobs.
- Users and the AI Agent may both create/edit workflow drafts. Agent output is a typed proposal, not an authorization.
- The canvas must support real node/edge interactions, labelled branches, graph validation, keyboard alternatives, and clear execution visualization.
- Backend validation, authorization, approval binding, and dispatch remain authoritative.
- Prototype execution must be visibly simulated. No real Windows machine-changing action is authorized by this task.

## Performance standard
Performance claims must be measured on a stated browser/OS/hardware configuration with reproducible graph fixtures and interaction scenarios. A 60 Hz frame budget (about 16.7 ms) is a useful target, not a verified result. Use 10-, 50-, and 100+-node synthetic fixtures where applicable; do not claim support or FPS without evidence.

## Validation
- Documentation-only change; no runtime code, dependencies, API, or package lock changes.
- Validate file links, skill frontmatter, scope consistency, and changed-file list.
- Runtime tests are not applicable. CI status must be checked for the PR head before reporting CI verification.
- Local Gemini CLI skill discovery is not claimed; it must be verified in the user's host environment after merge if needed.

## Out of scope
- Building the Visual Workflow Builder UI or Workflow Engine.
- Selecting or installing a graph library.
- Framework migration.
- Enabling script execution or any real PC-changing capability.
- Changing authentication, authorization, data retention, provider, or network exposure behavior.

## Next step
After review/merge, use this skill to conduct a bounded UX/technical discovery and prototype task for the Angular Visual Workflow Builder.
