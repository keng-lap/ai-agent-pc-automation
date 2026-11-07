---
name: documentation-decisions
description: Create or update project documentation, architecture notes, decision records, phase plans, task status, and handoffs while preserving approved scope and traceability.
---

# Documentation and Decisions

## Source of truth
- Read the current document and its linked decisions before editing.
- Keep approved decisions, proposals, assumptions, and unresolved questions visibly distinct.
- Do not convert a proposal into a requirement or record an unapproved choice as decided.
- Use Thai for user-facing UI/content requirements; use concise English for technical skill files and code-facing conventions where appropriate.

## Editing
- Make the smallest coherent change. Avoid duplicating existing rules; link to the authoritative document.
- Preserve dates, task IDs, PR/commit references, and evidence accurately.
- Update status only when supported by repository or Product Owner evidence.
- Record what changed, why, scope, exclusions, validation, and remaining gates.
- Check relative links, headings, terminology, and consistency with README, PROJECT, ROADMAP, and active phase docs.

## Decision records
For each material decision capture: ID, status (approved/proposed/deferred/rejected), decision owner, date, context, chosen option, rationale, consequences, and related tasks.
Only the Product Owner can approve Product Owner decisions. An AI assistant must not approve its own proposal.

## Handoff
End task documentation with the verified current state, open questions/gates, and one concrete next step. Do not claim a task or phase is closed without explicit closeout evidence.
