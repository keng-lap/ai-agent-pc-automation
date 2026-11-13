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
- Before recommending or integrating any external tool, AI provider, API, or reviewer, read `.agents/skills/evidence-first-tool-adoption/SKILL.md`; require independent usage evidence and end-to-end proof of the intended workflow before asking the Product Owner to configure credentials or adopting it.
- Inspect the full diff for unrelated changes, weakened tests, secrets, and scope expansion.
- Stop with BLOCKED when authorization, a security invariant, or meaningful verification is missing.

## Approval boundaries
- Never merge a PR or enable a real machine-changing capability without separate explicit Product Owner approval.
- Do not interpret “continue”, phase authorization, or successful Dry Run as authorization for real execution or merge.
- Independent security review must not be self-certified by the implementer.
- Do not claim external Gemini/Claude review unless actual review output is supplied or the reviewer integration was genuinely used.

Detailed engineering requirements are in docs/SECURE-DEVELOPMENT-STANDARD.md. Provider-specific instructions must not weaken that standard.

## AI-assisted automatic testing
- Follow docs/AI-ASSISTED-AUTOMATIC-TESTING.md for every code change.
- Before coding, map changed behavior to acceptance criteria and existing tests; write a test plan for positive, negative, boundary, and regression behavior as applicable.
- Add or update deterministic tests in the same task branch. For security rejections, assert denied requests make zero calls to side-effect handlers.
- Run focused tests, then the full relevant suite and configured checks. Inspect actual CI results after PR creation/update.
- AI-generated tests must assert independently grounded expected behavior; never weaken, delete, skip, or rewrite assertions merely to obtain a green result.
- Treat test-runner/CI output as authoritative. Report exact commands and PASS / FAIL / PENDING / NOT VERIFIED; never infer a pass.
- AI PR review or autonomous test-repair services that transmit repository data externally are not authorized by this workflow and require separate Product Owner approval.
