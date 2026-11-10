---
name: evidence-first-tool-adoption
description: Evaluate external tools, AI providers, integrations, and AI reviewers before recommending setup or making them part of project workflows. Use before adding providers, API keys, CI integrations, agents, or review automation.
---

# Evidence-First Tool Adoption

## Objective

Do not make the Product Owner spend time or money on an unproven tool. A tool is not "working" because it has an API, documentation, a successful installation, or a passing mock test. It is working only when it completes the intended user workflow and produces verifiable results.

## Mandatory gates — complete in order

### 1. Define the real job

- State the exact user problem and the workflow the tool must complete.
- Define observable acceptance criteria before implementation.
- For an AI PR reviewer, the job is to review an actual repository PR, identify actionable findings tied to changed lines, explain severity and evidence, and publish or deliver a review that a human can inspect.
- A health check, model-list response, HTTP 200, generated sample, unit test, or successful authentication is not proof that the intended job works.

### 2. Establish independent usage evidence

Before recommending adoption, find evidence beyond the vendor's API documentation:

- Prefer identifiable independent teams/projects or users describing real use in a comparable workflow.
- Look for concrete artifacts: public PR reviews, issue discussions, case studies with implementation detail, reproducible examples, or independently reported operational experience.
- Record source, date, what was actually used, and limitations.
- Separate evidence levels clearly:
  - **Documented capability**: vendor says the feature/API exists.
  - **Demonstrated**: a reproducible example works in a controlled test.
  - **Real workflow verified**: the tool completed the intended workflow on a real project artifact.
  - **Independent adoption evidence**: unrelated users/projects report using it in practice.
- Do not describe documented capability as proven adoption. If independent usage evidence cannot be found, say so and do not recommend production adoption.

### 3. Validate cheaply before asking the user to configure anything

- Prefer an existing authorized environment, public demo, free tier, mock, or disposable test repository.
- Do not ask the Product Owner to create an account, buy credits, configure billing, create an API key, or add repository secrets until the evidence review and test plan are presented and the user explicitly agrees.
- First test the smallest end-to-end slice. Keep it outside required CI and production workflows.
- Use the same provider, model, API version, SDK/REST path, payload shape, permissions, and network context intended for adoption. Do not infer compatibility from a different test path.
- Bound attempts, timeouts, spend, rate, and output size. State the stop condition before running.
- After two bounded attempts without a verified root cause, stop retries, report the evidence, and use the fallback. Do not create repeated speculative fix PRs.

### 4. Protect credentials and data

- Never put API keys, tokens, or credentials in source files, commits, issues, PR descriptions, prompts, screenshots, or logs.
- If a secret is genuinely required and the user has approved the integration, use the platform's designated secret store (for example, GitHub Actions Secrets); pass it only to the minimum job and step that need it.
- Never request that a user paste a secret into chat. Never echo secrets or raw provider responses that may contain sensitive data.
- Review permissions, fork behavior, event triggers, data retention, provider data handling, and outbound data before enabling an integration.
- Do not send private repository code, diffs, user data, or secrets to a third party without explicit approval.

### 5. Prove the intended workflow

For an AI reviewer or agent:

- Test against at least one real, non-sensitive PR or a deliberately constructed test PR in a disposable repository.
- Verify that output refers to actual changed files/lines and contains actionable, reproducible findings or correctly reports no findings.
- Include a known seeded defect and a known safe change to measure detection and false positives.
- Confirm failure modes are visible and fail closed: no fabricated review, no silent success, no false "approved" state.
- Have a human inspect the result. An agent must not claim independent review of its own work.
- Preserve a non-AI fallback (human review, static analysis, tests, or existing CI).

### 6. Decide and communicate

Use one of these explicit outcomes:

- **ADOPT** — all required evidence and end-to-end acceptance criteria passed; state exact scope and limitations.
- **PILOT** — independent usage evidence exists, but local end-to-end proof is incomplete; isolated pilot only, not a required gate.
- **DEFER** — evidence or access is insufficient; record what evidence would reopen the decision.
- **REJECT** — security, privacy, reliability, cost, or quality is unacceptable.

Report links and exact run/PR identifiers. Label each claim as documented, demonstrated, real-workflow verified, or independently evidenced. Never estimate completion time without a measured basis.

## Mandatory rules for AI review integrations

- A model being listed by an API or a request returning HTTP 200 does not prove review capability.
- A smoke test proves only the exact request it exercised; it does not prove PR retrieval, diff understanding, finding quality, or review delivery.
- Never make an unverified AI reviewer a required check or imply that it reviewed a PR.
- Keep AI review optional until real-PR acceptance criteria pass and the Product Owner explicitly approves adoption.
- When provider calls fail, report the exact observed status and run link; do not guess the cause or change model/API versions speculatively.
- Do not make the Product Owner repeatedly run diagnostics that the agent can retrieve from repository CI logs.

## Stop conditions

Stop the evaluation and switch to the fallback when:

- independent usage evidence is absent and cannot be verified;
- credentials, billing, or external data sharing would be needed before approval;
- two bounded attempts fail without a verified root cause;
- the intended workflow cannot be demonstrated;
- security, privacy, or reliability requirements cannot be met.

A stopped evaluation is not a project failure. Record the blocker and the evidence required to reconsider it.