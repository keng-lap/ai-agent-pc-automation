# P6-609-C Catalog Search Fix Evidence

## Problem
A natural-language install request for `DBeaver Community` reached the structured `software.install` intent correctly, but the WinGet source2 catalog search returned no candidates. The catalog query used the entire phrase as one contiguous substring. The catalog's display name is `DBeaver Community Edition` and its package ID is `DBeaver.DBeaver.Community`, so the space-separated phrase did not occur contiguously in either field.

## Change
- Tokenize the validated query into distinct Unicode word tokens.
- Require every token to match at least one of the Microsoft catalog's `name`, `id`, or `moniker` fields.
- Keep all search values parameter-bound; only the count of SQL predicates is assembled from the bounded token list.
- Preserve the existing exact-name/package-ID and name-prefix ranking.
- Keep Microsoft source2 as the only package identity source. Gemini still cannot supply trusted Package IDs, installer URLs, hashes, or commands.

## Regression coverage
- `DBeaver Community` resolves only `DBeaver.DBeaver.Community`.
- Search is case-insensitive and independent of word order.
- Every query word is required, preventing broad partial matches (for example, `DBeaver Enterprise` resolves the Enterprise package, not Community).

## Safety and verification status
- No WinGet command or installer was invoked.
- No TOTP approval, release authorization, worker execution, or live installation was performed.
- Automated regression tests were added. CI results must be checked on the resulting PR head before declaring the fix verified.
- PR #170 remains Draft and unmerged.
