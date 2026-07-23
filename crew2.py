from dotenv import load_dotenv
import os
import sys
import json
import argparse
from pathlib import Path
load_dotenv()

import asyncio
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ResultMessage,
)

# This repo is also a local SDK plugin (.claude-plugin/plugin.json) so the
# analyze-code Skill loads by absolute path, not by cwd. That matters when
# crew2.py runs as part of another repo's reusable-workflow call: cwd is the
# *reviewed* repo's checkout, but this script (and the plugin it's part of)
# are checked out separately, wherever this file itself actually lives.
PLUGIN_PATH = Path(__file__).parent


def require_env(name: str) -> str:
    """Fail fast with a clear message instead of a raw KeyError traceback."""
    value = os.environ.get(name)
    if not value:
        print(f"Error: {name} is not set. Add it to .env locally or as a repo secret in CI.", file=sys.stderr)
        sys.exit(1)
    return value


def resolve_target(args: argparse.Namespace) -> tuple[str, int]:
    """Determine (owner/repo, pr_number) from CLI args, env vars, or a GitHub Actions event payload."""
    if args.repo and args.pr:
        return args.repo, args.pr

    repo = os.environ.get("PR_REVIEW_REPO") or os.environ.get("GITHUB_REPOSITORY")
    pr_number = os.environ.get("PR_REVIEW_PR_NUMBER")

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not pr_number and event_path and os.path.exists(event_path):
        with open(event_path) as f:
            event = json.load(f)
        pr_number = (event.get("pull_request") or {}).get("number") or event.get("number")

    if not repo or not pr_number:
        raise SystemExit(
            "No target PR found. Pass --repo owner/name --pr N, set "
            "PR_REVIEW_REPO/PR_REVIEW_PR_NUMBER, or run inside a GitHub Actions "
            "pull_request event."
        )
    return repo, int(pr_number)


async def main():
    require_env("ANTHROPIC_API_KEY")
    github_token = require_env("GITHUB_TOKEN")

    parser = argparse.ArgumentParser(
        description="Review a GitHub pull request with an Explorer/Fixer/Reporter agent crew."
    )
    parser.add_argument("--repo", help="owner/repo, e.g. burakcoleman/jwks-extended-server")
    parser.add_argument("--pr", type=int, help="Pull request number")
    args = parser.parse_args()

    repo, pr_number = resolve_target(args)
    target = f"pull request #{pr_number} in {repo}"
    report_path = f"reports/{repo.replace('/', '-')}-pr{pr_number}.txt"

    had_error = False
    try:
        async for message in query(
            prompt=(
                f"Review {target}. "
                "Do this in exact order, every time: "
                "1) Use the explorer agent to get the PR diff and list code quality issues. "
                "2) If the explorer found no issues, skip straight to step 3. Otherwise, use the "
                "fixer agent to post a review comment for each real issue. Pass the explorer's "
                "findings to the fixer verbatim, in the exact 'path:line — [severity] issue — fix' "
                "format the explorer returned them in — do not summarize, reformat, or drop lines. "
                f"3) Use the reporter agent to write a summary to {report_path} and post the same "
                "summary as a comment on the pull request. Pass the explorer's findings and the "
                "fixer's actions (or 'no issues found' if step 2 was skipped) to the reporter "
                "verbatim as well."
            ),
            options=ClaudeAgentOptions(
                mcp_servers={
                    'github': {
                        'type': "http",
                        'url': "https://api.githubcopilot.com/mcp/",
                        'headers': {'Authorization': f"bearer {github_token}"},
                    }
                },
                allowed_tools=['Agent'],
                max_turns=40,
                plugins=[{"type": "local", "path": str(PLUGIN_PATH)}],
                agents={
                    'explorer': AgentDefinition(
                        description='Expert code reviewer. Use first, to fetch a GitHub PR diff and list code quality issues in the changed lines.',
                        prompt=(
                            f"Get the diff of {target} and list any code quality issues you find in the "
                            "changed lines. Before reviewing, check your agent memory for patterns, "
                            "conventions, and known false positives you've noted about this repo before, "
                            "and don't re-flag anything your memory says was already reviewed and "
                            "dismissed. After reviewing, update your memory with any new repo-specific "
                            "convention or recurring false-positive pattern you noticed — keep entries "
                            "short and concrete."
                        ),
                        tools=['mcp__github__pull_request_read'],
                        skills=['code-review-crew:analyze-code'],
                        memory='project',
                    ),
                    'fixer': AgentDefinition(
                        description='Expert developer and code fixer. Use second, after the explorer agent has reported issues, to post GitHub PR review comments with suggested fixes.',
                        prompt=(
                            f"Explorer found these issues on the changed lines of {target}. For each "
                            "real issue: create a pending review (pull_request_review_write, "
                            "method=create), add a line comment with a ```suggestion``` block via "
                            "add_comment_to_pending_review, then submit the pending review "
                            "(pull_request_review_write, method=submit_pending, event=COMMENT). Before "
                            "writing suggestions, check your agent memory for this repo's fix/style "
                            "conventions. After finishing, update your memory with any new convention "
                            "you had to infer."
                        ),
                        tools=[
                            'mcp__github__pull_request_review_write',
                            'mcp__github__add_comment_to_pending_review',
                            'mcp__github__pull_request_read',
                            'mcp__github__get_file_contents'
                        ],
                        memory='project',
                    ),
                    'reporter': AgentDefinition(
                        description='Report writer. Use last, after explorer and fixer have both finished, to summarize their findings into a report file and post them as a PR comment.',
                        prompt=(
                            f"Create a summary report of the explorer's findings and the fixer's "
                            f"actions for {target}. Write it to {report_path}. Then post the same "
                            "summary as a comment on the pull request using add_issue_comment "
                            f"(owner/repo: {repo}, issue_number: {pr_number})."
                        ),
                        tools=['Write', 'mcp__github__add_issue_comment'],
                        model='claude-opus-4-8',
                    ),
                },
            ),
        ):
            if isinstance(message, ResultMessage):
                print(f"Done: {message.subtype}")
                if message.is_error:
                    had_error = True
                    print(f"Error subtype: {message.subtype}", file=sys.stderr)
                    if message.errors:
                        print(f"Errors: {message.errors}", file=sys.stderr)
                    if message.api_error_status:
                        print(f"API error status: {message.api_error_status}", file=sys.stderr)
    except Exception as e:
        # Broad on purpose: the SDK raises plain Exception (not just
        # ClaudeSDKError) for some failures, e.g. an API-level error result
        # surfaced from receive_messages(). Catch everything here so CI logs
        # get a clean one-line message instead of a raw traceback.
        print(f"Agent crew failed to run: {e}", file=sys.stderr)
        sys.exit(1)

    if had_error:
        sys.exit(1)


asyncio.run(main())
