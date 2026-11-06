# P5-514 — Thai-default UX and API integration report

## Status

Implementation is in progress on `feat/P5-514-thai-default-ux-api-integration`.
This task was explicitly authorized by the Product Owner on 2026-11-07.
P5-512 (PR #63) and P5-513 (PR #64) are complete and merged.

## Implemented scope

- Added `POST /api/plans`, which accepts only the user's request text and the display language.
- Added `GET /api/plans/{plan_id}` for retrieving an exact P5-512 plan while its process-local 10-minute reference remains valid.
- The plan endpoint uses the existing deterministic planner, strict P5-512 plan schema/store, fixed P1 tool catalog, and dry-run-only handlers.
- The plan endpoint does not call Gemini, inspect Windows, inspect installed software, query package sources, download installers, or change the machine.
- The chat UI requests a plan after displaying Gemini's text reply. Gemini text is displayed as conversational content and is not parsed as an executable instruction or trusted policy.
- The UI shows the original request, backend interpretation, each proposed program and its fields, unresolved prerequisites/questions, status, and a visible dry-run/no-change notice.
- Thai is the default language; English remains selectable.
- No acknowledgement, cancel, approval, execute, install, or remove control/endpoint is added.

## Java development example

For `เตรียมเครื่องพัฒนา Java`, the deterministic planner proposes only the core JDK item. The JDK version remains unspecified and its status is `NEEDS_CLARIFICATION`. The UI asks which JDK version is wanted and whether the user wants a particular IDE or would like options first. An IDE is not silently added because it is a user choice.

## Data and safety boundaries

- The request and plan are returned to the active UI response; the plan store retains only the strict P5-512 per-program report in process memory.
- Plan references expire after 10 minutes and are invalidated by process restart.
- Source, dependencies, disk space, impact, and live machine state remain marked not checked/unknown.
- Client requests cannot set risk, permission, approval, handler, or execution metadata.
- The only dispatched handlers remain fixed dry-run mocks guarded by backend policy.
- No chat/task history, prompt archive, durable plan store, or browser storage is introduced.

## Verification

Tests have been added for Java plan creation, plan retrieval, rejection of client-supplied policy fields, invalid language, and absence of acknowledgement/execution routes. Frontend tests cover the Java review card and the plan API request.

The GitHub Actions CI result is pending PR creation. No local test run is claimed because this execution environment could not reach GitHub to clone the repository. The CI workflow remains the authoritative verification gate for Ruff, backend tests, frontend tests, and the frontend build.
