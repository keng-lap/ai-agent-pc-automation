# Repository Instructions for AI Coding Agents

Before acting, read README.md, docs/PROJECT.md, docs/ROADMAP.md, the active phase document (currently docs/PHASE-6.md), docs/SECURE-DEVELOPMENT-STANDARD.md, and task-specific decisions/architecture/review findings.

## Mandatory workflow
- Confirm current branch, base commit, working-tree state, task scope, and applicable Product Owner authorization.
- Preserve approved safety boundaries. Phase-level authorization is not capability-level authorization.
- For non-trivial/security-sensitive changes, complete a threat model and secure design before implementation using docs/templates/THREAT-MODEL-TEMPLATE.md.
- Define positive and negative tests. Prove rejected requests cannot reach side-effect handlers.
- Use fixed backend-owned tool IDs, strict typed schemas, policy checks, exact-action approvals, and fixed dispatch only. Never add arbitrary shell/PowerShell/CMD/script execution, dynamic imports, eval, or model-selected handlers.
- Use synthetic fixtures, mocks, spies, and isolated temporary directories. Never inspect or mutate the user's live PC.
- Run documented checks and relevant security tests. Report PASS, FAIL, PENDING, and NOT VERIFIED accurately.
- Inspect the full diff for unrelated changes, weakened tests, secrets, and scope expansion.
- Stop with BLOCKED when authorization, a security invariant, or meaningful verification is missing.

## Approval boundaries
- Never merge a PR or enable a real machine-changing capability without separate explicit Product Owner approval.
- Do not interpret “continue”, phase authorization, or successful Dry Run as authorization for real execution or merge.
- Independent security review must not be self-certified by the implementer.
- Do not claim external Gemini/Claude review unless actual review output is supplied or the reviewer integration was genuinely used.

Detailed engineering requirements are in docs/SECURE-DEVELOPMENT-STANDARD.md. Provider-specific instructions must not weaken that standard.
