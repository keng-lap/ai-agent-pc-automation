# Agent Skills Foundation

## Status

**Six original workspace skills merged via PR #102.** The repository-specific frontend-design skill is introduced separately by task P6-602. All skills are documentation/procedure files; they do not change application runtime behavior, backend authorization, or Windows execution capabilities.

## Format and discovery

Skills use the Agent Skills format: one folder per skill with a required SKILL.md containing YAML name and description frontmatter. They are stored under .agents/skills/.

- Gemini CLI documents workspace skill discovery for its supported host/version. Follow the [official Gemini CLI Agent Skills guide](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md) and verify activation locally before relying on it.
- ChatGPT does **not** automatically discover or activate repository skill files. When acting on this project, ChatGPT should consult docs/CHATGPT-AGENT-GUIDE.md and retrieve only the relevant SKILL.md and reference files through the connected repository source.
- Skill activation and workspace trust remain host/version-specific; a merged file is not evidence of activation in a particular agent.

## Included skills

| Skill | Responsibility |
|---|---|
| project-context | Load source of truth, current phase, decisions, scope, and handoff |
| git-workflow | Branch, diff, commit, PR, and merge discipline |
| testing-qa | Test selection, evidence, regression, and coverage limitations |
| windows-safety | Machine-action boundaries, backend authority, approval, and fail-closed rules |
| debugging-token | Root-cause diagnosis and safe context/token compression |
| documentation-decisions | Consistent docs, decision records, status, and handoff |
| frontend-design | Thai-first UX, Angular UI, design system, accessibility, workflow canvas, and measured frontend performance |

## Operating principles

- GEMINI.md remains the project-wide instruction and source-of-truth entry point for hosts that load it. ChatGPT's repository workflow is described separately in docs/CHATGPT-AGENT-GUIDE.md.
- Skill descriptions are short and distinct to support host discovery. Detailed procedures load only when the host supports and activates them, or when an assistant explicitly retrieves them.
- No skill includes executable scripts, automatic machine actions, network calls, or credentials.
- These skills do not affect the Gemini Chat API used by the running application. Runtime behavior still requires backend-owned instructions supplied by the application.
- The frontend-design skill governs design/implementation quality only. It does not authorize framework migration, new dependencies, runtime execution capabilities, new providers, external data flows, or changes to safety/privacy policy.

## Local verification (Gemini CLI)

If using Gemini CLI, verify skill discovery in the installed version using its documented commands and workspace-trust requirements. Do not assume that a command supported by one host/version is available in PowerShell or another ChatGPT interface. Do not install third-party skills or grant broader filesystem/tool access as a workaround.

**Verification status:** repository files are added on the P6-602 branch; merge and local activation in a Gemini CLI host have not yet been verified.
