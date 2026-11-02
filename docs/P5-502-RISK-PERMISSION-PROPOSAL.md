# P5-502 — Risk Classification and Permission-Level Proposal

## Status

**Proposal for Product Owner review.** Documentation only. This proposal does not authorize runtime implementation, real machine access, installation, removal, downloads, or execution.

Depends on P5-501 threat model. This proposal incorporates the Product Owner's direction: for the current project stage, the Agent may only prepare and report dry-run plans. It must explicitly identify every program it proposes to install before presenting the dry-run result.

## 1. Product Owner direction and governing boundary

The only currently permitted operating mode is **P1 — Dry-run / plan and report**.

- No real installation or removal.
- No download, package-manager invocation, installer launch, process creation, shell, PowerShell, CMD, script, registry, filesystem, network, or system-setting operation.
- No machine inspection to discover installed software, versions, disk space, privileges, or system state.
- No provider integration, live model call, credentials, or external data transfer.
- A dry-run result is a report about the proposed plan, not evidence that the machine is ready or that an installation succeeded.
- P2/P3 or any execution-capable permission is not enabled or implied. Any future proposal requires a separate Product Owner decision and the approved Phase 5/Phase 6 gates.

The existing `software.install` and `software.remove` catalog entries remain dry-run/mock only.

## 2. Proposed risk classification

Risk describes the potential impact of the requested capability; it does not grant permission.

| Class | Meaning | Examples | Current treatment |
|---|---|---|---|
| R0 — Informational | Explain or display information without machine access or state change | Explain what Java JDK is | May provide an informational response; no machine inspection |
| R1 — Planning | Produce a proposed plan from user input and bounded static knowledge | List software needed for a Java development setup | P1 dry-run report only |
| R2 — Machine inspection | Read local machine/application/system state | Check installed versions or available disk space | Blocked in this stage |
| R3 — Machine change / privileged | Install/remove software or change files, processes, registry, services, network, security, or system settings | Install JDK; uninstall an application; run administrator command | Blocked; mock/dry-run description only |

Classification is based on the highest-impact operation in the request. A request containing multiple actions inherits the highest class. Unknown or ambiguous actions fail closed and are not silently downgraded.

## 3. Proposed permission levels

| Level | Meaning | Allowed now? |
|---|---|---|
| P0 — No machine capability | General explanation based only on supplied input/static knowledge | Yes |
| P1 — Dry-run plan and report | Build a structured proposed action plan; do not interact with the machine | **Yes — only active project permission** |
| P2 — Read-only machine inspection | Read local machine state | No |
| P3 — Machine-changing execution | Install/remove or otherwise change the machine | No |

P0/P1 are planning/reporting capabilities, not evidence of human identity. P2/P3 are listed to make the boundary explicit, not as implementation authorization. The local API token is not a human identity credential and is not consent.

## 4. Required Agent output: explicit software installation list

For every installation request, the Agent must show an **Installation Plan** before the dry-run outcome. It must enumerate each program individually. It must not hide a package list inside a generic phrase such as "install development tools".

Each item must include:

1. Program name and purpose.
2. Version: exact version only when specified or supported by trusted, available static data; otherwise state `Not specified` or `Needs user decision`.
3. Why the program is proposed and which user requirement it satisfies.
4. Proposed source or package manager, clearly marked as a proposal and not checked live.
5. Dependencies and installation order, or `Unknown / not verified`.
6. Expected impact such as administrator requirement, restart possibility, or system-wide scope only when known; otherwise mark unknown.
7. Approximate disk requirement only when supported by available data; otherwise `Not available`.
8. Dry-run status and any blocker or question.

The report must distinguish:
- **User request** — what the user asked for.
- **Agent interpretation** — the exact software list the Agent believes is required.
- **Proposed plan** — ordered, per-program actions and dependencies.
- **Dry-run result** — what could be described, what is blocked, and what needs clarification.

The Agent must not add optional software, extensions, runtimes, drivers, or utilities without identifying them as optional and explaining why. It must not silently expand scope. If a necessary program or version is ambiguous, ask the user before finalizing the plan.

### Example format (illustrative only)

User request: "Prepare this PC for Java development."

| Order | Program | Version | Purpose | Proposed source | Dependency | Status |
|---:|---|---|---|---|---|---|
| 1 | Git | Needs user decision | Source control | Not checked | None known | Needs clarification |
| 2 | JDK | Needs user decision | Java compiler/runtime | Not checked | None known | Needs clarification |
| 3 | Apache Maven | Needs user decision | Build tool | Not checked | JDK likely required; not verified | Needs clarification |
| 4 | Visual Studio Code | Needs user decision | Code editor | Not checked | None known | Optional — ask user |

This is an example of report structure, not a recommended fixed bundle. The Agent must not treat these programs, versions, sources, or ordering as approved defaults.

## 5. Dry-run outcome vocabulary

Every proposed program/action receives exactly one primary status:

- `PLANNED` — a bounded plan can be described from available information; nothing was executed.
- `NEEDS_CLARIFICATION` — user input is required, such as program/version/edition choice.
- `BLOCKED` — prohibited by current permission boundary or missing safety prerequisite.
- `UNSUPPORTED` — the requested operation is outside the fixed supported tool catalog.

The overall result must say **Dry-run only — no changes made**. It must never use success wording such as "installed", "removed", "completed installation", or "machine ready". It may say "plan prepared" or "would request".

A report must state its evidence limits: no live source availability, current package version, installed-state, compatibility, disk-space, or privilege check has occurred unless a future separately approved capability explicitly provides that evidence.

## 6. Backend enforcement requirements (proposal)

- Risk and permission metadata are owned by the backend's fixed tool definitions.
- The backend independently validates tool identity, typed parameters, bounds, and permission before dispatch.
- The model cannot select or raise its own permission level.
- The frontend cannot grant permission by changing UI state or submitting a client-supplied risk label.
- Unknown tool IDs, unknown fields, invalid parameters, missing policy, and inconsistent metadata fail closed before a handler is reached.
- Dry-run handlers must be side-effect-free and use fixed mock/planning logic; they must not invoke operating-system commands or external services.
- No generic command string, executable path, script body, or arbitrary argument vector is accepted as an execution instruction.

These are design requirements for later P5-504/P5-507 review, not permission to implement them in this task.

## 7. Acceptance criteria

- The only active permission is P1 Dry-run; P2/P3 remain disabled.
- R0–R3 are impact classifications, not permission grants.
- Every installation request produces an explicit per-program Installation Plan before its dry-run result.
- Version, source, dependency, ordering, and impact uncertainty are visibly marked; the Agent does not invent facts.
- Optional additions are separated and explained; ambiguous scope requires clarification.
- The report explicitly states that no machine changes or live checks occurred.
- No runtime code, tests, command execution, downloads, provider calls, or machine inspection are part of P5-502.
- P5-503/P5-504 must refine the confirmation and backend contracts without weakening this dry-run-only boundary.
- Product Owner review is required before this proposal is treated as an approved decision.

## 8. Open decisions for Product Owner

1. Approve or revise the R0–R3 definitions.
2. Confirm P1 Dry-run as the only currently active permission and keep P2/P3 disabled.
3. Confirm the mandatory per-program Installation Plan fields and status vocabulary.
4. Decide whether optional software should be shown separately by default or omitted unless explicitly requested.

No decision is assumed from silence.
