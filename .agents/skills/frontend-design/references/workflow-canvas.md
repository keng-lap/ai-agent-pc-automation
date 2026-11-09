# Workflow Canvas Design and Engineering Reference

## Product model
- A Job is the schedulable/manageable unit with identity, owner, configuration, and run history.
- A Workflow Definition is a versioned graph belonging to a Job.
- A Node is one typed step in that graph.
- An Edge is a directed connection from an output port to an input port.
- A Job Run is one execution attempt against an immutable workflow version.
- A Node Execution is one node's attempt within a Job Run.
- The Visual Workflow Builder is the editor for the graph; it is not itself a node and does not execute work.

## Canvas interaction model
Required core interactions for a full builder:
- Add a node from the library by drag/drop and by keyboard-accessible add action.
- Move nodes with pointer and keyboard-accessible position controls.
- Connect output handles to compatible input handles by dragging a visible connector.
- Reconnect an existing edge, select/delete edges, and label conditional edges.
- Pan, zoom, fit-to-view, select, multi-select, duplicate, and delete nodes.
- Undo/redo and unsaved-change indication.
- Minimap and auto-layout where they improve navigation; neither should obscure the graph.
- Support copy/paste only after validating IDs and references; never duplicate approval identity or execution history.

## Node and port contract
Each node type must define a backend-owned contract with:
- Stable type ID and schema version.
- Thai display name, concise purpose, category, and help text.
- Input/output port IDs and data types.
- Required and optional configuration fields with constraints.
- Declared side-effect class and permission/risk metadata.
- Timeout, retry, cancellation, and idempotency behavior where applicable.
- Output schema and failure semantics.
- Whether it can be used in Dry Run and what Dry Run means for that node.

The frontend may render metadata and provide early validation, but it must not invent an executable node type or elevate a node's permission.

## Graph validation
Validate locally for immediate feedback and again on the backend as the authority:
- Unknown node type or unsupported schema version.
- Duplicate/missing node and port IDs.
- Missing required configuration.
- Invalid port/data-type connections.
- Multiple edges into a single-input port where prohibited.
- Missing required start/trigger node.
- Unreachable nodes and orphaned branches.
- Cycles unless the backend contract explicitly supports a bounded loop construct.
- Unhandled failure paths where required.
- Invalid branch labels or incomplete conditional outputs.
- Self-connections and invalid edge references.
- Unsupported fan-out/fan-in and ambiguous merge semantics.

Show the affected node/edge and a Thai explanation with a suggested correction. Do not silently auto-repair a graph in a way that changes execution semantics.

## Branching and control flow
- Use explicit ports for outcomes such as success/failure or true/false.
- Label branches in plain Thai (for example ผ่าน / ไม่ผ่าน, สำเร็จ / ล้มเหลว).
- Show the default/fallback path where one exists.
- Do not imply that two branches run in parallel unless the workflow contract says so.
- Distinguish conditional branching from parallel execution.
- Retry, delay, wait, and loop constructs must have bounded limits and visible stop conditions.

## Execution visualization
- The canvas displays persisted execution state; it does not drive execution.
- Keep Job Run ID and workflow version visible in run detail.
- Node states should be explicit: not started, queued, running, awaiting approval, succeeded, failed, skipped, cancelled, blocked, or retrying.
- Use both text/icon and color to indicate status.
- Show start/end time, duration, safe summary, and structured error details.
- Keep log volume bounded and redact secrets. Do not expose raw credentials, tokens, environment secrets, or unrestricted script contents.
- Updating a running node's status must not move nodes or reset the user's viewport/selection.
- Distinguish design-time validation, Dry Run simulation, and actual execution.

## AI Agent integration
- The Agent creates or edits a typed Workflow Definition proposal using a documented API/schema; it does not manipulate the DOM or simulate mouse/keyboard events.
- The proposal must be validated and shown as a draft before publish/run.
- Preserve user edits. If the Agent proposes a new version while the user has unsaved changes, present a conflict/reconciliation flow instead of overwriting.
- Explain why each node and edge exists in user-readable language.
- Agent suggestions do not constitute approval. Approval and dispatch are backend-controlled and bound to immutable, exact action data.

## Versioning and persistence
- Saved workflow versions are immutable snapshots once published.
- Draft edits have explicit save/dirty state and conflict handling.
- Each Job Run references the exact workflow version and content digest.
- Node execution records reference the run and node identity.
- Retention, local storage, access control, backup, and deletion behavior must follow approved persistence policy.
- Do not persist secrets or raw prompts/responses in workflow definitions or execution logs.

## Technology evaluation
For an Angular application, compare candidate graph/canvas libraries or a small custom implementation using a documented decision matrix:
- Angular compatibility and supported Angular/TypeScript versions.
- Maintenance activity, release cadence, issue response, and license.
- Accessibility and keyboard support.
- Edge routing, custom nodes/handles, minimap, zoom/pan, selection, and layout support.
- Graph size and interaction performance under reproducible tests.
- Bundle size, tree-shaking, build compatibility if relevant, and dependency risk.
- Styling/theming flexibility and integration with existing design tokens.
- Export/import and schema independence.

Do not select React Flow merely because it is popular; it is a React library and does not directly satisfy an Angular-native application. A framework migration is out of scope unless explicitly approved. Keep the workflow graph schema independent of the chosen canvas library.
