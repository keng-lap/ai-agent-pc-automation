# UX and UI Quality Checklist

## Before implementation
- [ ] Identify the primary user, task, and success outcome.
- [ ] Review existing application screens and reuse the current design system.
- [ ] Define information hierarchy and navigation.
- [ ] Write realistic Thai labels, helper text, and error messages.
- [ ] Identify safety-sensitive actions and approval boundaries.
- [ ] Define empty, loading, error, blocked, and success states.

## Visual quality
- [ ] Clear page hierarchy and one obvious primary action per context.
- [ ] Consistent spacing, typography, color, iconography, borders, and elevation.
- [ ] Canvas has sufficient working space; side panels can be resized/collapsed if useful.
- [ ] Node categories are recognizable without relying on color alone.
- [ ] Connections are directional, readable, and do not overlap labels unnecessarily.
- [ ] No dead controls, placeholder copy, accidental horizontal scroll, or clipped Thai glyphs.
- [ ] Long job names, node names, parameters, and errors remain readable.

## Usability
- [ ] First-time user can identify how to add a node and connect it.
- [ ] Every node explains purpose, required inputs, outputs, and side effects.
- [ ] Invalid connections are prevented or clearly rejected with a correction hint.
- [ ] Keyboard alternatives exist for important drag-only actions.
- [ ] Unsaved changes and version differences are visible.
- [ ] Dry Run, approval, publish, schedule, and execute are distinct actions.
- [ ] User can understand current run status and which node needs attention.

## Accessibility and responsive behavior
- [ ] Semantic labels and accessible names.
- [ ] Visible keyboard focus and logical tab sequence.
- [ ] Text and controls meet contrast requirements.
- [ ] State is not conveyed by color alone.
- [ ] Reduced motion and browser zoom work.
- [ ] Thai text does not clip at target viewport sizes.
- [ ] Smaller viewport behavior is intentional, not accidental.

## Performance and reliability
- [ ] Build and relevant tests run with exact commands recorded.
- [ ] Drag, connect, pan, zoom, and status updates are exercised.
- [ ] 10/50/100+ node synthetic fixtures are used where applicable.
- [ ] No unbounded event handlers, subscriptions, or logs.
- [ ] Save/load and interrupted network behavior are exercised where in scope.
- [ ] Performance results include environment and reproducible method.

## Safety and trust
- [ ] Prototype execution is clearly simulated.
- [ ] AI-created workflows are drafts until validated.
- [ ] Frontend validation is not treated as backend authorization.
- [ ] Risky actions show exact scope and require backend-enforced approval.
- [ ] No arbitrary command/script execution or hidden privilege escalation.
- [ ] Logs and UI never reveal secrets.
