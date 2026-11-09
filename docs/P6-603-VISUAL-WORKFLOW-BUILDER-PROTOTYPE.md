# P6-603 — Visual Workflow Builder UX Prototype

## Status
**In progress — bounded frontend-only prototype.** Product Owner authorization was given on 2026-11-09. This task does not authorize a Workflow Engine or any real PC-changing capability.

## Objective
Validate the Job Designer user experience and the library-independent workflow graph interaction model before designing or implementing the Workflow Engine.

## Scope
- Add a Thai-first Workflow Builder workspace to the existing Angular application.
- Provide a Node Library, graph Canvas, selected-node/edge Properties panel, and clear prototype/safety state.
- Support palette drag-and-drop and click-to-add, node dragging, direct output-to-input edge dragging plus click/keyboard connection, labelled true/false branches, selection, editing, deletion, and zoom controls.
- Use synthetic in-memory graph data only.
- Keep the graph model independent of any canvas library.
- Add no third-party dependency and no backend API integration.

## Explicit exclusions
- No Workflow Engine, Job persistence, Job scheduling, publish, or execution API.
- No actual software discovery, install/remove, script execution, shell, process, filesystem, registry, or Windows action.
- No Agent-generated workflow API or provider call.
- No durable browser/backend storage; prototype graph resets on page reload.
- No selection of a production graph library. The native SVG/HTML implementation is a UX spike, not a final architecture decision.

## Prototype graph model
- Node: stable local ID, typed category, label, description, canvas position.
- Edge: stable local ID, source node ID, source output port ID, target node ID.
- Node type and output-port metadata are frontend-local synthetic fixtures. Backend-owned contracts remain authoritative and are not defined by this prototype.
- Conditional nodes expose explicit yes and no outputs.
- The prototype rejects self-connections, duplicate connections, multiple edges into one input, and cycles. These are usability checks only, not backend validation.

## User journey
1. Open "ออกแบบ Workflow" from the authenticated local workspace.
2. Review the sample graph and its labelled branch paths.
3. Add a node by dragging from the library or clicking the library item.
4. Move a node by dragging its header.
5. Connect an output port to another node's input port.
6. Select a node or edge and edit/remove it in the Properties panel.
7. Zoom the canvas or reset its view.
8. Return to chat using the side navigation.

## Acceptance criteria
- Existing Angular 22 architecture and visual language are reused.
- Main interactions work without a new dependency or backend request.
- Branch outcomes are explicit and readable.
- Keyboard-accessible click-to-add and click-to-connect alternatives are provided for drag operations.
- Thai labels and long descriptions wrap without clipping.
- Layout adapts to narrower viewports; canvas remains independently scrollable.
- Prototype clearly states it is not saved and does not call the backend or control Windows.
- Existing chat, authentication, and Dry Run behavior remain unchanged.
- Build, unit tests, and relevant browser E2E checks are run and recorded; failures are reported without concealment.
- No 60 FPS, 100+ node, accessibility-pass, or production-readiness claim without reproducible evidence.

## Technology note
A small native SVG + HTML canvas prototype avoids a graph-library dependency while testing core interactions. It does not settle the production graph technology. A separate decision must compare Angular-compatible candidates against maintenance, licensing, Angular compatibility, accessibility, custom ports/edges, bundle size, and measured graph performance before any dependency is approved.

## Handoff
After review, collect Product Owner feedback on the user journey and node contracts. Only then prepare a separate Workflow Definition/API contract and a library-selection decision. Workflow Engine work remains a separate task and requires its own authorization and safety review.
