# Code Review Crew

A GitHub PR review bot built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Python) and GitHub's MCP server. A top-level orchestrator delegates to three subagents through the SDK's `Agent` tool:

1. **Explorer** — fetches a GitHub PR diff (`mcp__github__pull_request_read`) and lists code quality/security issues in the changed lines. Guided by the `code-review-crew:analyze-code` Skill, loaded from this repo's own local plugin — see [Reviewing other repos](#reviewing-other-repos) for why it's packaged as a plugin instead of a plain `.claude/skills/` entry. Has persistent memory of the reviewed repo's conventions and past false positives.
2. **Fixer** — turns each real issue into an inline GitHub PR review comment with a `suggestion` block, and submits the review. Has persistent memory of this repo's fix/style conventions.
3. **Reporter** — summarizes the Explorer's findings and the Fixer's actions into a per-PR report file, and posts the same summary as a PR comment (`mcp__github__add_issue_comment`) so it's visible without digging through CI logs.

The orchestrator prompt names all three agents explicitly and in the order they must run, so the pipeline doesn't depend on the model guessing which subagent to call next.

> **Note:** `mcp__github__add_issue_comment` is the documented tool name for GitHub's official MCP server; it hasn't been verified yet against the specific `api.githubcopilot.com/mcp/` endpoint this project uses (the review-comment tools already in use here — `pull_request_review_write`, `add_comment_to_pending_review` — differ slightly from that server's public docs, so naming isn't 1:1 across versions). Confirm on the first real run.

## Project structure

```
.
├── crew2.py                          # Orchestrator: delegates to explorer/fixer/reporter subagents
├── .github/workflows/
│   ├── review.yml                    # Reusable (workflow_call): the actual review job
│   └── pr-review.yml                 # Thin caller: runs review.yml for this repo's own PRs
├── .claude-plugin/plugin.json        # Makes this repo a local SDK plugin named "code-review-crew"
├── skills/analyze-code/SKILL.md      # The Explorer's diff review checklist, loaded via the plugin
├── .claude/agent-memory/             # This repo's own explorer/fixer memory (see below — every
│   ├── explorer/MEMORY.md            # reviewed repo gets its own, not shared through this one)
│   └── fixer/MEMORY.md
├── .env                               # ANTHROPIC_API_KEY, GITHUB_TOKEN (not committed)
└── reports/                           # Per-PR report files, gitignored (also posted as a PR comment)
```

## Setup

```bash
pip install claude-agent-sdk python-dotenv
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-api-key-here
GITHUB_TOKEN=your-github-token-here
```

`GITHUB_TOKEN` needs read access to pull requests and write access to submit reviews on the target repo.

## Usage

### Manually

```bash
python3 crew2.py --repo owner/name --pr 42
```

Fetches the diff, posts inline review comments for real issues, writes a summary to `reports/<owner>-<repo>-pr<N>.txt`, and posts that same summary as a comment on the PR. `--repo`/`--pr` can also be supplied via the `PR_REVIEW_REPO`/`PR_REVIEW_PR_NUMBER` env vars.

### Automatically, via GitHub Actions

`.github/workflows/pr-review.yml` calls the reusable `review.yml` workflow on every `opened`/`synchronize`/`reopened` pull request event in *this* repo. `crew2.py` reads the target repo and PR number straight from the Actions event payload (`GITHUB_REPOSITORY` and `GITHUB_EVENT_PATH`), so no flags are needed in CI.

Required repo secrets:

- `ANTHROPIC_API_KEY`
- `PR_REVIEW_GITHUB_TOKEN` (optional) — a fine-grained PAT with pull request read/write scope. Falls back to the default `GITHUB_TOKEN` if unset; use a PAT if the GitHub MCP server rejects the default token's scope.

### Reviewing other repos

`review.yml` is a [reusable workflow](https://docs.github.com/en/actions/using-workflows/reusing-workflows) (`on: workflow_call`), so any other repo you own can call it without copying `crew2.py` or the `analyze-code` Skill — those get checked out from `code-review-crew` at run time into a `_crew/` subdirectory, while the reviewed repo's own checkout is what `.claude/agent-memory/` and `reports/` are written into and committed back to. Each repo accumulates its *own* memory — `code-review-crew`'s `.claude/agent-memory/` never sees another repo's findings.

The Skill still has to be loadable from that `_crew/` checkout path rather than the reviewed repo's cwd, which plain `.claude/skills/` can't do (it's cwd-relative). That's why `code-review-crew` is structured as a local [SDK plugin](https://code.claude.com/docs/en/agent-sdk/plugins) instead: `crew2.py` passes `plugins=[{"type": "local", "path": <its own directory>}]`, computed from `Path(__file__).parent` so it's correct wherever the file was checked out, and the Explorer references the skill by its namespaced name, `code-review-crew:analyze-code`. Verified with a live one-turn `query()` call that the plugin and skill both show up in the SDK's init message regardless of cwd.

To wire up a new repo:

1. Add this workflow to that repo, e.g. `.github/workflows/pr-review.yml`:

   ```yaml
   name: Agentic PR Review

   on:
     pull_request:
       types: [opened, synchronize, reopened]

   permissions:
     contents: write
     pull-requests: write

   jobs:
     review:
       uses: burakcoleman/code-review-crew/.github/workflows/review.yml@main
       secrets: inherit
   ```

2. Add the `ANTHROPIC_API_KEY` secret to *that* repo. `secrets: inherit` only passes through secrets that already exist on the calling repo — personal-account repos (not an org) don't share secrets automatically, so this is a one-time step per repo.
3. `permissions:` must be declared in the *caller's* workflow (as above) — a reusable workflow's own token permissions are capped by whatever the caller grants, they can't be expanded from inside `review.yml`.

`GITHUB_TOKEN` doesn't need a per-repo secret: GitHub mints one automatically, scoped to whichever repo the job is actually running in — including when running through a reusable workflow call.

## How the agents connect

Unlike a hand-chained pipeline (separate `query()` calls passing return values between them), `crew2.py` defines all three roles as `AgentDefinition`s and runs a single top-level `query()`. Each subagent is scoped to only the tools it needs:

```python
agents={
    "explorer": AgentDefinition(..., tools=["mcp__github__pull_request_read"], skills=["code-review-crew:analyze-code"], memory="project"),
    "fixer": AgentDefinition(..., tools=["mcp__github__pull_request_review_write", ...]),
    "reporter": AgentDefinition(..., tools=["Write", "mcp__github__add_issue_comment"], model="claude-opus-4-8"),
}
```

The orchestrator only has the `Agent` tool and delegates the actual work; each subagent runs in its own isolated context — only its final message returns to the orchestrator.

### Why not agent teams?

The Claude Agent SDK also supports [agent teams](https://code.claude.com/docs/en/agent-teams) (teammates that message each other directly via `SendMessage`, coordinating on a shared task list). It's a better fit for independent, exploratory work — parallel code review from different angles, competing debugging hypotheses — not for this pipeline, where each stage strictly depends on the previous one's output. Agent teams are also still experimental, built around an interactive terminal session with a human lead, and carry meaningfully higher token cost. For a headless CI job that must complete reliably, the deterministic sequential-subagent approach above is the right fit.

The one real fragility in the sequential approach: the fixer and reporter never receive the explorer's findings as structured data, only whatever the orchestrator relays into their prompt. The orchestrator prompt is explicit about passing findings verbatim (see `crew2.py`) to keep that handoff from drifting.

## Memory

The `explorer` and `fixer` subagents are defined with `memory='project'`, which gives each one a persistent directory (`.claude/agent-memory/<agent>/`) it reads before starting and writes to when it learns something — repo-specific conventions, known false positives, fix/style patterns. This is a built-in Claude Agent SDK feature (part of "auto memory"): Read/Write/Edit tools and the read/write instructions are injected into the subagent automatically, on top of whatever `tools=[...]` restricts.

**Why this needs an extra CI step:** each Action run starts from a clean checkout, so anything the agents write to `.claude/agent-memory/` only helps future runs if it's committed back to the repo. `pr-review.yml`:

1. Checks out the **default branch**, not the PR merge ref — the crew never reads local files (everything goes through the GitHub MCP server), so the checkout exists only to give memory a place to live and be committed.
2. After the crew runs, commits any changes under `.claude/agent-memory/` and pushes them straight to the default branch (`git pull --rebase` first to reduce race conditions between overlapping runs).

This requires `contents: write` permission (not just `pull-requests: write`), which the workflow now requests. It also means the memory files are visible, versioned, and diffable — you can watch what each agent has learned over time in the repo's commit history. Trade-off: this needs write access to the default branch, so it won't work if `main` has branch protection rules that block direct pushes (in that case, either open a PR for memory updates instead, or fall back to caching `.claude/agent-memory/` with `actions/cache` and never committing it).

## Reliability

- **Real failures fail the run.** `ResultMessage.is_error` is checked; a failed review now exits non-zero (with `.errors`/`.api_error_status` logged) instead of always reporting `Done` and exiting 0 regardless of outcome.
- **Missing env vars fail fast** with a clear message instead of a raw `KeyError` traceback.
- **SDK/connection failures** are caught broadly (`except Exception`, not just `ClaudeSDKError`) and reported instead of crashing with an unhandled traceback — confirmed necessary live: an API-level error result (401 from a malformed `ANTHROPIC_API_KEY` secret) surfaced from the SDK as a plain `Exception`, not a `ClaudeSDKError` subclass, so the narrower catch would have missed it.
- **`max_turns=40`** bounds the crew so a stuck or looping agent can't run indefinitely or blow up cost.
- **`timeout-minutes: 15`** on the Action job is a hard ceiling, instead of relying on the runner's default 6-hour timeout.
- **Memory persistence is non-blocking** (`continue-on-error: true`): a push race or branch-protection rejection on the memory-sync step doesn't fail the job when the actual PR review already succeeded.

Deliberately out of scope for now: automatic retries on transient API errors (rate limits, overload). The SDK already retries some transient failures internally; adding our own retry loop would double token cost for marginal benefit at this stage.
