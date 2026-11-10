# Claude Code Project Instructions

Read AGENTS.md and docs/SECURE-DEVELOPMENT-STANDARD.md before making changes. Also read the active phase document and task-specific decisions/review findings.

For non-trivial or security-sensitive work:
- Complete threat model and secure design before coding.
- Define negative tests proving rejected requests never reach side-effect handlers.
- Preserve local-first, loopback-only, fixed-handler, no-arbitrary-command, and capability-specific approval boundaries.
- Use synthetic fixtures and isolated temporary directories; never inspect or mutate the user's live PC.
- Run applicable documented checks; distinguish PASS, FAIL, PENDING, and NOT VERIFIED.
- Inspect the full diff and stop as BLOCKED if a required security property cannot be proven.

Do not merge, enable real execution, widen permissions, or change approved data flows without explicit Product Owner authorization. The detailed requirements in docs/SECURE-DEVELOPMENT-STANDARD.md are authoritative.
