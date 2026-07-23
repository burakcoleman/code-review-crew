from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.environ['ANTHROPIC_API_KEY']

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, ResultMessage




async def main():
    async for message in query(
        prompt=(
            "Review pull request #1 in burakcoleman/jwks-extended-server. "
            "Do this in exact order: "
            "1) Use the explorer agent to get the PR diff and list code quality issues. "
            "2) Use the fixer agent to post a review comment for each real issue the explorer found. "
            "3) Use the reporter agent to write a summary of the explorer's findings and the fixer's "
            "actions to report.txt. "
            "Run all three agents, in that order, every time."
        ),
        options=ClaudeAgentOptions(
            mcp_servers={
                'github':{
                    'type': "http",
                    'url': "https://api.githubcopilot.com/mcp/",
                    'headers': {'Authorization': f"bearer {os.environ['GITHUB_TOKEN']}"},
                }
            },
            allowed_tools=['Agent'],
            agents={
                'explorer': AgentDefinition(
                description='Expert code reviewer. Use first, to fetch a GitHub PR diff and list code quality issues in the changed lines.',
                prompt= "Get the diff of pull request #1 in burakcoleman/jwks-extended-server and list any code quality issues you find in the changed lines.",
                tools=['mcp__github__pull_request_read'],
                skills=['analyze-code'],
                ),
                'fixer': AgentDefinition(
                    description='Expert developer and code fixer. Use second, after the explorer agent has reported issues, to post GitHub PR review comments with suggested fixes.',
                    prompt=""" Explorer found these issues on the changed lines of pull request #1 in burakcoleman/jwks-extended-server. "For each real issue: create a pending review (pull_request_review_write, 
method=create), add a line comment with a ```suggestion``` block via 
add_comment_to_pending_review, then submit the pending review 
(pull_request_review_write, method=submit_pending, event=COMMENT).""",
                    tools=[
                        'mcp__github__pull_request_review_write',
                        'mcp__github__add_comment_to_pending_review',
                        'mcp__github__pull_request_read',
                        'mcp__github__get_file_contents'
                    ],
                ),
                'reporter': AgentDefinition(
                    description='Report writer. Use last, after explorer and fixer have both finished, to summarize their findings into report.txt.',
                    prompt='Create a report and write it to report.txt using explorer finding and fixer summary.',
                    tools=['Write'],
                    model='claude-opus-4-8',
                ), 
            },
        ),
    ):
        if isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")

asyncio.run(main())