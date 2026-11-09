# Frontend Performance Reference

## Performance is measured, not asserted
Do not use fast, smooth, 60 FPS, 100 nodes, or production-ready as evidence. Record the tested commit, browser, OS, hardware class, graph fixture, scenario, repetitions, and observed metrics.

## Interaction budget
For pointer-driven canvas interactions, avoid long main-thread tasks. A 60 Hz display has a frame budget of about 16.7 ms; this is an engineering target, not a claim that every machine must sustain 60 FPS.

Measure:
- Frame-time distribution during node drag, edge creation, pan, and zoom.
- Long tasks and main-thread blocking.
- Input-to-paint latency where tooling permits.
- Canvas update and edge recomputation cost.
- Initial route load and editor chunk size.
- Memory growth during repeated editing and run-status updates.

## Implementation guidance
- Keep graph state normalized by stable node/edge IDs.
- Separate durable graph data from transient viewport, selection, hover, and drag state.
- Update only the moved node and affected edges where possible.
- Avoid cloning the entire graph on every pointer event.
- Avoid synchronous layout/routing algorithms inside pointer-move handlers.
- Batch or schedule expensive geometry work; cancel stale work.
- Avoid repeated layout reads mixed with DOM writes.
- Avoid excessive Angular change detection triggered by pointer movement; use suitable OnPush/signals/zone patterns consistent with the existing codebase and verify behavior.
- Keep event listeners/subscriptions scoped and cleaned up.
- Debounce persistence and never persist every pointer pixel.
- Keep API calls out of high-frequency pointer events.
- Use CSS transforms for viewport movement where appropriate.
- Do not add Web Workers, virtualization, or complex caches until profiling demonstrates a bottleneck and the design remains accessible.

## Reproducible graph fixtures
At minimum, create synthetic fixtures for:
- Small workflow: 10 nodes, several branches.
- Medium workflow: 50 nodes, mixed node types and edges.
- Large workflow: 100+ nodes, realistic branching and moderate edge density.

These are test fixtures, not promises about supported production limits. Define edge count and topology as well as node count.

## Suggested quality gates
Set final thresholds only after baseline measurement on the agreed target environment. A reasonable initial target for a desktop prototype:
- No lost pointer events, stuck drag state, or visibly delayed edge attachment.
- No repeated full-page render/layout during a local node drag.
- No unbounded memory growth after repeated add/move/connect/delete cycles.
- No blocking computation on the main thread for routine graph edits.
- Stable selection and viewport while execution status updates arrive.

If a project chooses a numeric frame-time or FPS gate, record the measurement tool, sample duration, percentile, and test hardware. Do not present a nominal 60 FPS target as verified without evidence.
