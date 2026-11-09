# P5-518 — Visual Dry-Run Workflow

## Status
Product Owner authorized the bounded frontend UX implementation on 2026-11-09.

## Goal
Present the existing P1 approval-gated Dry Run lifecycle as a node-based workflow inspired by n8n, making the current state and next required action easy to understand on desktop and mobile.

## Scope
- Add a five-node visual flow to each existing plan review: request received, plan created, eligibility checks, authenticator approval, and backend Dry Run result.
- Derive every node state only from the current frontend plan response and local request lifecycle.
- Show pending, ready, blocked, in-progress, and completed states with text labels and accessible semantics.
- Keep the existing program list, clarification flow, authenticator step-up, approval API, and dry-run report.
- Thai remains the default; provide English labels through the existing language switch.
- Responsive layout: connected horizontal nodes on wide screens and a vertical connected flow on narrow screens.

## Explicit exclusions
- No backend/API/agent/handler changes and no new execution capability.
- No real Windows commands, machine inspection, downloads, installs, removals, or system changes.
- No new provider, network flow, durable history, telemetry, or persistence.
- No claim of per-node live progress: the current approval API returns a single response and does not stream execution events. While the request is pending, the UI may show only that the request is being processed; final success is shown only after a valid backend response with the Dry Run result.
- No Phase 6 authorization.

## Acceptance criteria
1. The flow contains exactly five ordered, labelled nodes.
2. The flow accurately distinguishes plan completeness, user-presence challenge, approval request in progress, and confirmed Dry Run result.
3. Unknown, incomplete, or blocked plans never appear as successful or ready.
4. Every status is conveyed by text as well as visual styling.
5. Thai and English labels are available.
6. Mobile layout remains readable without horizontal scrolling.
7. Existing no-machine-change notice and absence of real execution controls remain intact.
8. Frontend unit tests, build, and existing desktop/mobile Playwright suites pass in CI.
9. No backend or security boundary changes are included.

## Validation limitations
GitHub Actions is the authoritative automated validation. Product Owner local Windows browser verification remains separate from CI evidence.
