---
name: debugging-token
description: Diagnose errors and reduce unnecessary context/token use when reviewing logs, stack traces, diffs, API payloads, test output, or coding-agent conversations without losing diagnostic evidence.
---

# Debugging and Token Efficiency

## Diagnose first
1. Identify the failing command, component, first causal error, and expected behavior.
2. Inspect the smallest relevant source and surrounding context before proposing a fix.
3. Separate root cause, symptoms, hypotheses, and confirmed facts.
4. Prefer a minimal reproducible case and the smallest safe change.
5. After a fix, run the narrow regression test and required broader checks.

## Compress safely
- Remove repeated banners, duplicate stack frames, progress noise, and unrelated passing output.
- Keep exact error messages, file paths, line numbers, exit codes, failing test names, relevant inputs, and the first causal stack frame.
- For diffs, summarize unchanged context but retain every changed line relevant to correctness, security, and scope.
- Never truncate or paraphrase away security failures, destructive-command details, approval state, data-loss warnings, or evidence needed to reproduce a bug.
- Ask for a targeted excerpt only when repository/tool evidence cannot provide it.

## Token discipline
- Lead with the answer or action; avoid repeated history and filler.
- Use compact tables/lists only when they improve comparison.
- Do not send screenshots when concise text output is sufficient; request images only when visual evidence is necessary.
- Do not claim token savings without measuring comparable input/output usage on the same task and model settings.
- Caveman-style terse wording is a presentation preference, not permission to omit reasoning, caveats, safety gates, or verification.
