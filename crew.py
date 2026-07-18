from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.environ['ANTHROPIC_API_KEY']

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage


async def run_explorer():
    findings = ""
    async for message in query(
        prompt='scan sample_utils.py. List the issue you find.',
        options=ClaudeAgentOptions(
            allowed_tools=['Read', 'Glob', 'Grep'],
            skills=["analyze-code"],
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    findings += block.text
    return findings


async def run_fixer(findings):
    fixerdid= ''
    async for message in query(
        prompt=f"Read sample_utils.py. Fix these issues found by a previous review:\n{findings}",
        options=ClaudeAgentOptions(
            allowed_tools=['Read', 'Edit'],
            permission_mode='acceptEdits'
        ),
    ):
        if isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    fixerdid += block.text
    return fixerdid

async def run_reporter(findings, fixer_summary):
    async for message in query(
        prompt=f"Explorer findings:\n{findings}\n\nFixer summary:\n{fixer_summary}\n\nCreate a report and write it to report.txt.",
        options= ClaudeAgentOptions(
            allowed_tools=['Write'],
            permission_mode='acceptEdits',
        ),
    ):
        if isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")
                    
            


async def main():
    findings = await run_explorer()
    print("Explorer found:\n", findings)

    fixer_summary = await run_fixer(findings)   
    print("Fixer did:\n", fixer_summary)

    await run_reporter(findings, fixer_summary)  


asyncio.run(main())
