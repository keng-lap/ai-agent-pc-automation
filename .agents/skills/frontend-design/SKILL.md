---
name: frontend-design
description: Design, implement, and review polished, accessible, high-performance product interfaces in this repository. Use for Angular UI, UX flows, design systems, visual workflow builders, interaction design, responsive behavior, and frontend performance.
---

# Frontend Design

## Mission
Build a coherent, production-quality interface that is visually distinctive, immediately understandable to non-technical users, and responsive under realistic interaction. Visual polish, usability, accessibility, correctness, and performance are equal quality dimensions. Do not optimize one by quietly sacrificing another.

This skill is repository-specific. It supplements and never overrides approved project decisions, GEMINI.md, the active phase/task scope, and safety rules.

## Mandatory context before design or implementation
1. Read GEMINI.md, docs/CHATGPT-AGENT-GUIDE.md when acting as ChatGPT, docs/PROJECT.md, docs/ROADMAP.md, the active task/phase document, and relevant approved decisions.
2. Inspect the current Angular app, routes, components, global styles, assets, dependencies, tests, and recent merged UI work. Do not assume a remembered screenshot or old component map is current.
3. Read relevant references in this skill folder: design-system.md, workflow-canvas.md for node/edge editors, performance.md, and ux-quality-checklist.md.
4. Identify current design tokens and reusable components before introducing new ones. Preserve product identity unless the task explicitly approves a redesign.
5. State the bounded task and acceptance criteria. Do not silently expand a prototype into runtime execution functionality.

## Product design principles

### Clarity before cleverness
- Default UI language is Thai. Use concise, plain Thai for labels, help text, errors, confirmations, and empty states.
- A control must communicate what it does, what input it needs, and what happens next.
- Avoid unexplained technical jargon, ambiguous icons, vague labels, and color-only meaning.
- Prefer progressive disclosure: essential actions first; advanced settings remain collapsed until requested.
- Use consistent terminology across navigation, forms, dialogs, notifications, logs, and documentation.
- Make destructive, irreversible, privileged, external, or machine-changing consequences explicit before approval.

### Distinctive, coherent visual quality
- Design a deliberate visual hierarchy: typography, spacing, density, alignment, contrast, surfaces, borders, shadows, and motion must work as one system.
- Aim for a refined professional automation product, not a generic admin template or an unmodified component-library demo.
- Use a restrained palette with semantic status colors. Do not rely on gradients, glow, glass effects, oversized headings, or decoration to simulate quality.
- Use consistent iconography and meaningful labels. Icon-only controls need an accessible name and tooltip.
- Avoid visual clutter, unnecessary nested cards, excessive borders, and inconsistent corner radii.
- Use realistic product content and states in prototypes; do not use lorem ipsum.

### Interaction must be real and predictable
- Every visible control must work or be clearly marked unavailable in the prototype. No dead buttons, fake links, or decorative controls that imply functionality.
- Provide visible focus, hover, pressed, selected, disabled, loading, success, warning, and error states where applicable.
- Support keyboard operation for primary tasks and sensible focus management for dialogs and menus.
- Confirm destructive changes; provide undo where practical.
- Prevent invalid actions early and explain how to fix them.
- Preserve user work during refresh, navigation, failed requests, and recoverable errors where approved storage permits.

### Accessibility is part of implementation
- Use semantic HTML and correct labels, roles, and accessible names.
- Maintain WCAG 2.2 AA contrast targets for text and interactive controls.
- Never communicate state through color alone; pair color with text, icon, pattern, or shape.
- Ensure keyboard access, visible focus, logical tab order, reduced-motion support, and adequate hit targets.
- Respect browser zoom and text scaling. Avoid fixed-height containers that clip Thai text.
- Include accessible announcements for meaningful asynchronous updates; avoid announcing every high-frequency canvas movement.

## Repository technology constraints
- The existing frontend is Angular. Use the repository's installed Angular version, TypeScript configuration, routing, testing setup, and established patterns.
- Do not introduce React, React Flow, another framework, state-management library, UI kit, or graph library without a documented compatibility/performance assessment and explicit task approval where scope or dependencies change.
- For node/edge canvas requirements, evaluate Angular-compatible options against workflow-canvas.md; verify maintenance, Angular compatibility, licensing, bundle impact, accessibility, and interaction performance before selecting.
- Prefer existing dependencies and native browser capabilities when they satisfy requirements.
- Keep components focused, typed, testable, and consistent with Angular conventions already used by the codebase.
- Keep UI state separate from authoritative backend policy. The browser may display and edit a proposal; it must not grant permissions or decide whether a Windows action is safe.

## Workflow Builder UX contract
When designing a Visual Workflow Builder:
- Treat the builder as an editor for a Job's versioned workflow definition, not as a Node itself.
- Provide a Node Library, large Canvas, selected-node Properties panel, and execution/validation panel.
- Users can drag nodes onto the canvas, connect handles by dragging visible edges, reconnect edges, branch paths, select/multi-select, move, zoom, pan, fit-to-view, and use a minimap when useful.
- Edges must be visible, directional, labelled when branching (for example ผ่าน / ไม่ผ่าน), and route cleanly around nodes. Do not imply a connection where none exists.
- Provide keyboard alternatives or accessible controls for adding and connecting nodes; drag-only operation is insufficient.
- Validate node types, ports, required inputs, cycles, unreachable nodes, missing branches, and invalid connections. Explain errors in Thai and identify the affected node/edge.
- Offer undo/redo, auto-layout, duplicate, delete, copy/paste where safe, unsaved-change indication, and version history according to scope.
- Clearly distinguish draft, validated, Dry Run, awaiting approval, running, succeeded, failed, cancelled, and blocked states.
- Display per-node progress and logs without making the canvas jump or re-layout unexpectedly.
- AI Agent-generated workflows must arrive as a validated draft definition through an explicit application contract. The Agent must not simulate mouse input or bypass the workflow engine.
- Editing a workflow must never execute it. Publishing, scheduling, and running are separate actions with explicit consequences.
- Dry Run must be labelled as simulation and must not be presented as a real installation or machine change.

## Agent and safety boundaries
- Treat all AI-generated labels, node definitions, parameters, expressions, and connections as untrusted proposals.
- The backend owns the canonical workflow schema, allowed node types, validation, authorization, risk classification, approval binding, and dispatch.
- Frontend validation improves usability, but backend validation is authoritative.
- Never add arbitrary shell/PowerShell/CMD execution, arbitrary script execution, dynamic imports, model-supplied handler names, unrestricted filesystem/process/registry access, or privilege escalation as a UI shortcut.
- Hiding a control is not an authorization boundary.
- Risky actions require exact-action approval enforced by the backend. Approval must bind to immutable workflow/run/node/action parameters and relevant artifact digests.
- Preserve local-first and loopback-only constraints. Do not introduce remote access, external data flows, or new providers through UI work without explicit approval.
- Prototype data must be synthetic or isolated fixtures. Do not inspect or mutate the user's live Windows machine during design/testing.

## Performance engineering
- Treat responsiveness as a product requirement. Measure before and after; do not claim 60 FPS or 100+ nodes without reproducible evidence.
- Keep pointer-move and drag operations lightweight. Avoid rebuilding the entire application state or re-rendering every node for a local position change.
- Use stable IDs, bounded updates, isolated node renderers where appropriate, and avoid expensive work inside pointer-move handlers.
- Separate canvas viewport transforms from document persistence. Debounce or batch persistence; do not send API requests for every pointer movement.
- Avoid layout thrashing, repeated DOM measurement, unbounded subscriptions, memory leaks, and large synchronous computations on the main thread.
- Use virtualization or level-of-detail only when profiling shows it is needed; preserve usable edges, selection, and keyboard navigation.
- Lazy-load large editor features when it improves initial load without harming navigation.
- Respect reduced-motion preferences; keep animation short, purposeful, and interruptible.
- Define and test target hardware/browser, graph size, interaction scenario, and measurement method before setting thresholds.
- See performance.md.

## Required design workflow
1. Discover — inspect current UI, design tokens, app architecture, constraints, user tasks, and existing tests.
2. Specify — write the user journey, information architecture, key states, interaction rules, and measurable acceptance criteria.
3. Prototype — build a usable prototype with realistic data and working core interactions; isolate mock data and simulated execution.
4. Review — inspect visual hierarchy, Thai text wrapping, keyboard/accessibility, error states, empty states, and responsive behavior.
5. Measure — run build, unit/E2E checks, and repeatable performance scenarios. Record actual evidence and limitations.
6. Integrate — connect only to approved APIs/contracts; preserve backend authority and existing safety controls.
7. Handoff — document changed files, design decisions, dependency choices, tests, performance evidence, known gaps, and next approval.

## Definition of Done
- [ ] User journey and acceptance criteria are documented.
- [ ] Existing app architecture and design system were reused or justified changes recorded.
- [ ] UI is coherent, polished, Thai-first, and understandable without developer knowledge.
- [ ] All visible controls work or are explicitly marked prototype-only/unavailable.
- [ ] Empty, loading, success, warning, error, disabled, and confirmation states are handled where relevant.
- [ ] Keyboard, focus, contrast, reduced-motion, and text-scaling checks are addressed.
- [ ] No unapproved framework, dependency, provider, API, or security-boundary change was introduced.
- [ ] Build and relevant unit/E2E tests pass, or failures/skips are reported exactly.
- [ ] Performance claims are backed by measurements from the stated environment.
- [ ] No real Windows machine-changing operation was performed.
- [ ] Handoff records limitations and required Product Owner approval.

## Reporting
Report briefly in Thai: what changed, what was actually tested, performance evidence if measured, known gaps, and next approval. Distinguish prototype behavior from production/backend behavior. Never claim a visual review, accessibility pass, FPS target, or test result without evidence.
