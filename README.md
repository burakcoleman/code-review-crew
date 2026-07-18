# Code Review Crew

A small multi-agent pipeline built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Python). Three agents hand work off to one another in a single process:

1. **Explorer** — scans a target file and lists code quality issues (read-only: `Read`, `Glob`, `Grep`). Uses the `analyze-code` Agent Skill to guide what it looks for.
2. **Fixer** — takes the Explorer's findings and applies fixes (`Read`, `Edit`, auto-accepting edits).
3. **Reporter** — takes both the findings and the fix summary and writes `report.txt`.

## Project structure

```
.
├── crew.py                          # Orchestrates Explorer -> Fixer -> Reporter
├── sample_utils.py                  # Sample target file the crew reviews/fixes
├── .claude/skills/analyze-code/     # Agent Skill used by the Explorer
│   └── SKILL.md
├── .env                             # ANTHROPIC_API_KEY (not committed)
└── report.txt                       # Generated after running crew.py
```

## Setup

```bash
pip install claude-agent-sdk python-dotenv
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Usage

```bash
python3 crew.py
```

This runs the full pipeline against `sample_utils.py` and writes the results to `report.txt`. Each agent call uses the Claude API, so running it has a small cost.

## How the agents connect

Each agent is an `async` function that runs a `query()` call from the SDK and collects the model's text output into a string. `main()` awaits them in sequence, passing the return value of one directly into the next:

```python
findings = await run_explorer()
fixer_summary = await run_fixer(findings)
await run_reporter(findings, fixer_summary)
```

Because all three run in the same process, data is passed in memory — no intermediate files are needed between steps.
