# P6-608 — Professional Workflow Builder UX Blueprint

## Status
**Design blueprint proposed; implementation and production execution are not authorized by this document.**

## 1. Objective

Define a coherent, professional, desktop-first Workflow Builder that is approachable to non-programmers while providing the precision expected from a technical automation studio.

The Builder is an editor for a Job's versioned Workflow Definition. It is not a Node, scheduler, execution engine, authorization boundary, or Windows control surface.

Product principles:
1. Clarity before feature density.
2. Safe-by-default, with visible consequences before approval.
3. Graph editing must be predictable, reversible, and testable.
4. Design-time validation, Dry Run simulation, approval, publish, and actual execution are distinct states/actions.
5. The frontend presents proposals and status; backend contracts remain authoritative.
6. Desktop is the current target. Mobile Builder interaction is a later optional project, not a requirement for this blueprint.

## 2. Users and primary journeys

### Personas
- **Everyday user:** describes an outcome, assembles a workflow from understandable nodes, configures fields, and reviews results without needing to write code.
- **Power user:** builds branches, reuses sub-workflows, configures retry/timeout behavior, inspects node inputs/outputs, and diagnoses failures.
- **AI Agent:** proposes or revises a typed workflow draft through an application contract. It does not manipulate the canvas DOM or authorize execution.
- **Reviewer / Product Owner:** reviews validation findings, risk, exact actions, version changes, and approval requirements.

### Core journeys
1. Create Job → add nodes → connect paths → configure properties → validate → save draft.
2. Ask Agent for a workflow → review a diff/proposal → accept selected changes → validate → save draft.
3. Open an existing Job → inspect immutable versions → create a new draft from a version → edit and validate.
4. Inspect a Job Run → see the exact workflow version → follow node states → inspect sanitized logs and structured errors.
5. Resolve a validation or run failure → navigate directly to affected node/edge → apply a correction → validate again.

## 3. Information architecture

The desktop workspace has four primary regions:

- **Node Library (left):** searchable, categorized node catalogue; concise purpose and side-effect indicator; drag-to-add plus keyboard/click add.
- **Workflow Canvas (center):** graph editing, navigation, selection, branches, minimap when useful, and contextual controls.
- **Properties Inspector (right):** configuration for the selected node or edge, grouped into Basic, Advanced, Input/Output, and Safety/Behavior sections.
- **Execution & Validation Panel (bottom or docked):** validation findings, Dry Run simulation, selected Job Run details, node timeline, and sanitized logs.

A compact top command bar provides Job identity, workflow version, dirty/saved state, undo/redo, validation, save, and context-appropriate actions. Publish, schedule, and actual run controls must remain absent or visibly unavailable until separately authorized and implemented.

Panels must be independently collapsible. Canvas space is the primary workspace. Panel state should not reset graph selection or viewport unexpectedly.

## 4. Canvas interaction contract

### Required interactions
- Add from Node Library by drag/drop and click/keyboard action.
- Move a node by its dedicated drag handle; do not start canvas pan from interactive node content.
- Connect output to compatible input; show a clear preview and reject invalid targets.
- Reconnect either endpoint of an existing edge.
- Select one node/edge; multi-select with modifier/selection rectangle; move selected nodes as a group.
- Duplicate and delete selected nodes/edges with safe ID/reference regeneration.
- Pan with blank-space drag, middle mouse, or Space + drag; preserve node and edge gestures.
- Zoom with toolbar controls and Ctrl/Command + wheel; provide fit-to-view and reset.
- Minimap for orientation and navigation on larger graphs.
- Auto-layout as an explicit user action with preview/undo; never silently rearrange a graph during editing or execution updates.
- Undo/redo for graph mutations and property edits.
- Keyboard alternatives for add, select, move, connect, delete, zoom, and panel navigation.
- Visible dirty state and recovery from accidental edits where persistence policy permits.

### Gesture precedence
1. Node handle drag moves node(s).
2. Port drag creates/reconnects an edge.
3. Edge hit target selects an edge.
4. Blank canvas drag pans.
5. Space + drag and middle mouse explicitly pan.
6. Touch-specific gesture design is deferred to a separate mobile option.

Do not make a gesture depend only on color or an undiscoverable modifier. Show contextual hints and support pointer cancellation without leaving stuck drag/pan state.

### Graph navigation
- Fit-to-view includes all visible nodes with safe padding.
- Zoom is bounded and anchored around pointer/viewport center where feasible.
- Minimap reflects viewport and supports click/drag navigation without becoming the only navigation method.
- Selection, viewport, and scroll position remain stable when node execution status updates.

## 5. Node Library and configuration

### Library behavior
- Search by Thai/English label, category, and common user intent.
- Categories: Triggers, AI & Data, Logic, Approval, Software Hub, Script, Utilities, and Outcomes (only categories with approved node contracts are shown).
- Each item shows display name, one-line purpose, category, and a concise risk/side-effect marker.
- Distinguish available, planned, disabled, and unavailable node types. Do not expose a planned node as executable.
- Provide a detail view with required inputs, outputs, example, limitations, and Dry Run semantics.

### Properties Inspector
- Use typed forms generated from a versioned node schema; never ask users to enter arbitrary command fragments as a shortcut.
- Show required fields, constraints, defaults, examples, validation messages, and units.
- Group advanced options progressively; avoid overwhelming first-time users.
- Show input/output contracts and data mapping explicitly.
- Explain timeout, retry, cancellation, idempotency, and failure behavior when applicable.
- Preserve invalid draft values so users can correct them; do not silently coerce values that change meaning.
- For side-effecting nodes, show exact target, package/script identity, parameters, source, scope, and expected effect. Approval is backend-enforced and bound to immutable exact action data.

## 6. Validation and authoring feedback

Validation is layered:
- **Inline validation:** immediate field and connection feedback.
- **Graph validation:** explicit Validate action; reports all detectable graph-level findings.
- **Backend validation:** authoritative validation before any future publish/run action.

Validation checks include:
- Unknown node type or schema version.
- Missing/duplicate node and port IDs.
- Missing required configuration or invalid parameter values.
- Invalid port/data-type connections and prohibited fan-in/fan-out.
- Missing trigger/start node, unreachable nodes, orphaned branches.
- Cycles unless an explicitly bounded loop contract supports them.
- Incomplete conditional branches and missing fallback paths.
- Unhandled failure paths where required.
- Invalid references, self-connections, and ambiguous merge/parallel semantics.

Each finding identifies severity, affected node/edge, plain Thai explanation, and a suggested correction. Selecting a finding focuses the affected graph item. No automatic repair may change execution semantics without explicit user review.

Validation states: Not validated, Valid, Warning, Error, and Stale (graph changed after last validation). A successful frontend validation is not authorization.

## 7. Workflow lifecycle and versioning

Keep these concepts distinct:
- **Job:** manageable unit with identity, owner, settings, and run history.
- **Workflow Definition:** typed graph belonging to a Job.
- **Draft:** mutable working copy.
- **Saved Version:** immutable snapshot with version number and content digest.
- **Job Run:** one execution attempt referencing an exact immutable version.
- **Node Execution:** one node attempt within a Job Run.

Lifecycle labels:
- Draft / Unsaved changes
- Saved
- Validation failed / Validation passed
- Dry Run simulated
- Awaiting approval (only when future capability is separately enabled)
- Published (only after an approved publish contract exists)
- Running / Succeeded / Failed / Cancelled / Blocked (run states, not draft states)

Version history should show author/source (human or Agent), timestamp, summary, and changed nodes/edges/configuration. Compare versions with a readable graph/configuration diff. Rollback creates a new draft from a previous immutable version; it does not rewrite historical versions.

Conflict handling: never overwrite unsaved human edits with an Agent proposal or remote update. Present a diff and explicit reconciliation choices.

## 8. Dry Run, execution debugger, and Job Monitor

- Clearly label prototype/mock data and simulated outcomes.
- Dry Run must state exactly what is simulated and what is not; it must not launch a process, download/install software, or mutate Windows.
- A future real run must be driven by the backend Workflow Engine, never by canvas event handlers.
- A run view binds to Job Run ID and immutable Workflow Definition version.
- Node states: Not started, Queued, Running, Awaiting approval, Succeeded, Failed, Skipped, Retrying, Cancelled, and Blocked.
- Show timestamps, duration, safe summary, structured error code/message, retry attempt, and sanitized bounded logs.
- Provide follow/stop viewing controls separately from any future cancellation action. A cancel request must only be offered when the backend contract supports safe cancellation.
- Status updates must not change node positions, selection, or viewport.
- Logs must redact secrets and avoid unrestricted script contents, prompts, credentials, tokens, or environment values.

## 9. AI Workflow Assistant

- Agent output is a typed, schema-versioned Workflow Definition proposal.
- Show proposed changes as a reviewable diff: added/removed/changed nodes, edges, and properties.
- Explain in plain Thai why each node and branch is proposed.
- User can accept all, accept selected changes, or reject the proposal.
- Validate the accepted draft and preserve pre-existing user edits.
- The Agent cannot publish, approve, execute, or bypass backend validation/policy.
- Do not call the model on every drag, keystroke, or canvas edit. Invoke it only on explicit user request or a clearly defined assist action.

## 10. Reusable building blocks and advanced controls

Later capabilities, each requiring its own typed contract and task:
- Reusable Sub-workflow with explicit input/output schema and version pinning.
- Retry with bounded attempt count, backoff, and retryable error classification.
- Timeout and cancellation with documented cleanup/partial-result behavior.
- Error routes and compensation only where semantics are explicit.
- Variables and secret references through an approved secret-handling design; never store plaintext secrets in workflow definitions or logs.
- Templates with provenance, supported schema versions, risk labels, and safe sample data.

Do not imply parallel execution, loops, transactional rollback, or exactly-once execution unless the engine contract defines and tests those semantics.

## 11. Safety and trust boundaries

- Frontend validation is advisory; backend schema validation, authorization, policy, approval, dispatch, and audit are authoritative.
- Unknown node types and schema versions fail closed.
- AI-generated workflows remain drafts.
- A visual node does not enable its corresponding runtime capability.
- Side-effecting actions require capability-specific design, independent A4 review, tests, CI, and separate explicit Product Owner enablement approval.
- Exact-action approval must bind to the immutable workflow version, node identity, exact parameters, target, and artifact/package identity; stale or changed approvals are rejected.
- No arbitrary shell/PowerShell/CMD/script runner, unrestricted process/filesystem/registry manager, admin capability, or dynamic execution is authorized by this blueprint.
- Existing Install Software and Run Custom Script node concepts remain design-time prototypes only.
- Keep the application local-first and loopback-only; no mobile remote control or public exposure is introduced.

## 12. Accessibility, localization, and responsive policy

- Thai-first labels, instructions, empty states, errors, and confirmations; retain standard technical terms where clearer.
- WCAG 2.2 AA targets for contrast and keyboard operation.
- Never convey status by color alone; pair with text/icon/shape.
- Visible focus, logical tab order, reduced motion, browser zoom, and screen-reader labels.
- Keyboard alternatives for every essential canvas drag action.
- Test Thai glyph clipping, mixed Thai/English labels, long node names, and narrow inspector widths.
- Desktop is the current acceptance target. Mobile Builder is explicitly deferred as an optional follow-up; do not claim mobile-ready interaction from responsive CSS alone.

## 13. Performance and scale verification

Performance claims require reproducible evidence. A 60 Hz frame budget (~16.7 ms) is a target, not a verified guarantee.

Fixtures:
- Small: 10 nodes with multiple branches.
- Medium: 50 nodes with mixed node types and edges.
- Large: 100+ nodes with realistic branching and documented edge density.

Measure on a stated Windows/browser/hardware configuration:
- Node drag, group move, edge create/reconnect, pan, zoom, fit-to-view, minimap navigation.
- Frame-time distribution, long tasks, input-to-paint latency where available.
- Graph update/edge recomputation cost, initial route load/chunk size, memory growth.
- Repeated add/move/connect/delete cycles and execution-status updates.

Acceptance: no lost pointer events, stuck gestures, accidental node movement during pan, viewport jumps during status updates, unbounded event/listener/log growth, or routine blocking graph computation. Numeric FPS/frame-time gates are set only after baseline measurement and must state tooling, sample duration, percentile, and hardware.

## 14. Technology decision

- Keep Angular and current project conventions.
- Keep Workflow Definition schema independent of any canvas rendering library.
- Do not select React Flow for this Angular application without a separately approved framework decision.
- Before adding a graph library, compare Angular compatibility, maintenance, licensing, accessibility, custom node/edge support, minimap/layout support, performance, bundle impact, and migration cost.
- Prefer existing dependencies/native browser APIs if they meet the requirements. Record evidence and trade-offs before selecting a dependency.

## 15. Delivery sequence

This is a design and discovery sequence, not authorization for runtime execution.

| Step | Deliverable | Exit criteria |
|---|---|---|
| 608-A | UX blueprint and user journeys | Product Owner accepts scope and terminology |
| 608-B | Canvas interaction completion | Reconnect, multi-select/group move, undo/redo, fit-to-view, minimap, auto-layout behavior specified and tested |
| 608-C | Node schema + Properties UX contract | Typed config, ports, validation, risk metadata, Dry Run semantics documented |
| 608-D | Workflow Definition and version UX contract | Draft/save/version/diff/conflict behavior agreed |
| 608-E | Validation + Debugger UX prototype | Validation findings and mock run states usable end-to-end |
| 608-F | Technical discovery | Angular-compatible canvas decision, performance baseline, API contract proposal |
| Later | Workflow Engine and individual capabilities | Separate bounded approval, independent A4 review, tests, CI, and explicit enablement approval per capability |
| Optional later | Mobile Builder | Separate mobile interaction design and real-device acceptance |

## 16. Acceptance criteria for this blueprint

- [ ] Product model and terminology are consistent with the existing frontend design skill.
- [ ] Four workspace regions and top command hierarchy are specified.
- [ ] Canvas gestures, precedence, keyboard alternatives, and failure recovery are specified.
- [ ] Node Library and typed Properties behavior are specified.
- [ ] Validation rules and user-facing feedback are specified.
- [ ] Draft/version/run lifecycle and conflict handling are specified.
- [ ] Dry Run, mock data, execution visualization, and log redaction are distinguished.
- [ ] Agent proposals are reviewable drafts and cannot authorize execution.
- [ ] Accessibility, Thai-first UX, performance fixtures, and measurement rules are specified.
- [ ] Mobile is explicitly deferred.
- [ ] No runtime, API, dependency, persistence, security, or Windows execution behavior is changed or authorized.

## 17. References

- `.agents/skills/frontend-design/SKILL.md`
- `.agents/skills/frontend-design/references/design-system.md`
- `.agents/skills/frontend-design/references/workflow-canvas.md`
- `.agents/skills/frontend-design/references/performance.md`
- `.agents/skills/frontend-design/references/ux-quality-checklist.md`
- `docs/P6-605-JOB-MONITOR-PROTOTYPE.md`
- `docs/ROADMAP.md`
