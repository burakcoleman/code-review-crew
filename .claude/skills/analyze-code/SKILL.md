---
name: analyze-code
description: Finds code quality and potential bug issues in Python files. Use when a code review is requested.
---

## Task

Review the given Python file against the following criteria:

1. Error handling — are None / missing / empty values handled?
2. Type safety — what happens if a function receives an unexpected type?
3. Ambiguous sentinel values — do values like 0, "", or None conflate
   "no data" with "a genuine result"?
4. Missing type hints?

List your findings in the format "function name — issue (line number)".
