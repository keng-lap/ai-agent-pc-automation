# Agent Skills Foundation

## Status

**Merged into `main` via PR #102** (merge commit `c03f07f3eca762524fef254609b5c1707670006d`). The six workspace instruction skills are documentation/procedure files; they do not change application runtime behavior, backend authorization, or Windows execution capabilities.

## Format and discovery

Skills use the Agent Skills format: one folder per skill with a required `SKILL.md` containing YAML `name` and `description` frontmatter. They are stored under `.agents/skills/`.

- Gemini CLI documents workspace skill discovery for its supported host/version. Follow the [official Gemini CLI Agent Skills guide](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md) and verify activation locally before relying on it.
- ChatGPT does **not** automatically discover or activate repository skill files. When acting on this project, ChatGPT should consult `docs/CHATGPT-AGENT-GUIDE.md` and retrieve only the relevant `SKILL.md` files through the connected repository source.
- Skill activation and workspace trust remain host/version-specific; a merged file is not evidence of activation in a particular agent.

## Included skills

| Skill | Responsibility |
|---|---|
| `project-context` | Load source of truth, current phase, decisions, scope, and handoff |
| `git-workflow` | Branch, diff, commit, PR, and merge discipline |
| `testing-qa` | Test selection, evidence, regression, and coverage limitations |
| `windows-safety` | Machine-action boundaries, backend authority, approval, and fail-closed rules |
| `debugging-token` | Root-cause diagnosis and safe context/token compression |
| `documentation-decisions` | Consistent docs, decision records, status, and handoff |

## Operating principles

- `GEMINI.md` remains the project-wide instruction and source-of-truth entry point for hosts that load it. ChatGPT's repository workflow is described separately in `docs/CHATGPT-AGENT-GUIDE.md`.
- Skill descriptions are short and distinct to support host discovery. Detailed procedures load only when the host supports and activates them, or when an assistant explicitly retrieves them.
- No skill includes executable scripts, automatic machine actions, network calls, or credentials.
- These files do not affect the Gemini Chat API used by the running application. Runtime behavior still requires backend-owned instructions supplied by the application.
- These skills do not authorize Phase 6, real PC execution, mobile remote control, new providers/data flows, or any change to existing safety/privacy policy.

## Local verification (Gemini CLI)

If using Gemini CLI, verify skill discovery in the installed version using its documented commands and workspace-trust requirements. Do not assume that a command supported by one host/version is available in PowerShell or another ChatGPT interface. Do not install third-party skills or grant broader filesystem/tool access as a workaround.

**Verification status:** merge is confirmed; local activation in a Gemini CLI host has not been independently verified.
