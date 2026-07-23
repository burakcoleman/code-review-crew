# Code Review Crew

A GitHub PR review bot built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Python) and GitHub's MCP server. A top-level orchestrator delegates to three subagents through the SDK's `Agent` tool:

1. **Explorer** — fetches a GitHub PR diff (`mcp__github__pull_request_read`) and lists code quality/security issues in the changed lines. Guided by the `analyze-code` Agent Skill.
2. **Fixer** — turns each real issue into an inline GitHub PR review comment with a `suggestion` block, and submits the review.
3. **Reporter** — summarizes the Explorer's findings and the Fixer's actions into `report.txt`.

The orchestrator prompt names all three agents explicitly and in the order they must run, so the pipeline doesn't depend on the model guessing which subagent to call next.

## Project structure

```
.
├── crew2.py                          # Orchestrator: delegates to explorer/fixer/reporter subagents
├── mcp_server.py                     # Standalone hand-written stdio MCP server (learning exercise, not used by crew2.py)
├── sample_utils.py                   # Leftover sample file from an earlier single-file review flow
├── .claude/skills/analyze-code/      # Agent Skill used by the Explorer (diff review checklist)
│   └── SKILL.md
├── .env                              # ANTHROPIC_API_KEY, GITHUB_TOKEN (not committed)
└── report.txt                        # Generated after running crew2.py
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

```bash
python3 crew2.py
```

This reviews PR #1 in `burakcoleman/jwks-extended-server`: fetches the diff, posts inline review comments for real issues, and writes a summary to `report.txt`.

## How the agents connect

Unlike a hand-chained pipeline (separate `query()` calls passing return values between them), `crew2.py` defines all three roles as `AgentDefinition`s and runs a single top-level `query()`. Each subagent is scoped to only the tools it needs:

```python
agents={
    "explorer": AgentDefinition(..., tools=["mcp__github__pull_request_read"], skills=["analyze-code"]),
    "fixer": AgentDefinition(..., tools=["mcp__github__pull_request_review_write", ...]),
    "reporter": AgentDefinition(..., tools=["Write"], model="claude-opus-4-8"),
}
```

The orchestrator only has the `Agent` tool and delegates the actual work; each subagent runs in its own isolated context — only its final message returns to the orchestrator.
