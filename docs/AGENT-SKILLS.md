# Agent Skills Foundation

## Status

**Proposed implementation on branch `docs/SKILL-001-foundation`.** These are workspace-level instruction skills; they do not change application runtime behavior, backend authorization, or Windows execution capabilities.

## Format and discovery

Skills use the Agent Skills format: one folder per skill with a required `SKILL.md` containing YAML `name` and `description` frontmatter. They are stored under `.agents/skills/`, the interoperable workspace path supported by Gemini CLI as an alias alongside `.gemini/skills/`.

Official references:
- [Gemini CLI Agent Skills](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md)
- [Creating Agent Skills](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/creating-skills.md)
- [Agent Skill best practices](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills-best-practices.md)

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

- `GEMINI.md` remains the project-wide instruction and source-of-truth entry point. Skills provide focused procedures on demand; they do not replace or weaken it.
- Skill descriptions are short and distinct to support discovery. Detailed procedures load only when a skill activates.
- No skill includes executable scripts, automatic machine actions, network calls, or credentials.
- Skill activation/consent and workspace trust depend on the installed host agent/version. Verify discovery in the actual local environment before relying on activation.
- These files do not affect the Gemini Chat API used by the running application. Runtime behavior still requires backend-owned instructions supplied by the application.
- These skills do not authorize Phase 6, real PC execution, mobile remote control, new providers/data flows, or any change to existing safety/privacy policy.

## Local verification (Gemini CLI)

From the repository root after pulling this branch:

```text
/skills reload
/skills list
```

Confirm that all six names appear. If they do not, verify workspace trust and the host agent's supported skill discovery path. Do not install third-party skills or grant broader filesystem/tool access as a workaround.
