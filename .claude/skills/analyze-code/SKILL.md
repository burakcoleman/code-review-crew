---
name: analyze-code
description: Reviews a pull request diff for correctness, type-safety, and security issues in the changed lines only. Use when reviewing a PR diff before posting review comments.
---

## Task

You are given the diff of a pull request. Review only the changed (added/modified)
lines — do not flag pre-existing code outside the diff.

For each changed hunk, check:

1. Correctness — are None / missing / empty values handled? Off-by-one errors?
   Unhandled exceptions on the new code path?
2. Type safety — what happens on an unexpected input type? Are type hints
   present on new or changed function signatures?
3. Ambiguous sentinel values — do values like 0, "", or None conflate
   "no data" with "a genuine result"?
4. Security — hardcoded secrets or keys, weak or missing algorithm validation
   (e.g. accepting JWT `alg: none`, not pinning to an explicit allowlist like
   RS256), missing input validation, injection risk. Treat these as high
   severity — this repo handles JWKS/auth, so a crypto or validation mistake
   here is more costly than elsewhere.
5. Resource handling — unclosed files/connections, network calls without a
   timeout.

## Severity

Mark each finding `high`, `medium`, or `low`. Only `high` and `medium`
findings should become review comments — skip pure style nitpicks.

## Output format

One line per finding, in exactly this shape:

```
path/to/file:line — [severity] issue description — suggested fix
```

Example:

```
src/jwks.py:42 — [high] JWT algorithm not checked against an allowlist — restrict verification to RS256 explicitly
```

Report only real findings in this format — no prose summary, no headers, no
findings for lines outside the diff. This format is what the downstream
fixer agent parses to build its GitHub review comments, so keep it literal.
