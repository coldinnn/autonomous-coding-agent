import asyncio
from typing import Callable

import anthropic
from dotenv import load_dotenv

from tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

SYSTEM_PROMPT = """You are an autonomous coding agent. Your job is to fix GitHub issues by writing correct, minimal code changes.

Process:
1. Read the issue carefully to understand what needs to be fixed.
2. Explore the repository structure to understand the codebase layout.
3. Find the relevant files using list_directory, search_code, and read_file.
4. Read the relevant files thoroughly before making any changes.
5. Write a minimal, targeted fix using write_file.
6. Run the test suite to verify your fix works.
7. If tests fail, read the error output carefully and iterate.

Rules:
- Always read a file before writing it. Never write blindly.
- Write complete file contents when using write_file (not partial diffs).
- Be surgical — change only what's needed to fix the issue. No refactoring.
- Run tests after every change to verify correctness.
- Stop when tests pass or after 5 fix attempts. Explain what you did.
- If you cannot fix the issue, explain why clearly.
"""


class CodingAgent:
    def __init__(self, issue: dict, repo_path: str, emit: Callable):
        self.issue = issue
        self.repo_path = repo_path
        self.emit = emit
        self.client = anthropic.AsyncAnthropic()
        self.messages: list[dict] = []
        self.modified_files: set[str] = set()
        self.iterations = 0
        self.max_iterations = 30

    async def run(self) -> None:
        initial_content = (
            f"Please fix the following GitHub issue in the repository at `{self.repo_path}`.\n\n"
            f"**Issue #{self.issue['number']}: {self.issue['title']}**\n\n"
            f"{self.issue.get('body', '(no description)')}\n\n"
            f"Start by exploring the repository structure, then find and fix the problem."
        )
        self.messages.append({"role": "user", "content": initial_content})

        await self.emit({"type": "step", "message": "Agent starting — exploring repository..."})

        while self.iterations < self.max_iterations:
            response = await self._call_claude()

            # Emit thinking if present
            for block in response.content:
                if block.type == "thinking":
                    text = getattr(block, "thinking", "") or ""
                    if text:
                        await self.emit({"type": "thinking", "text": text})

            stop_reason = response.stop_reason

            if stop_reason == "refusal":
                await self.emit({"type": "step", "message": "Request was declined by safety classifier — stopping."})
                break

            if stop_reason in ("end_turn", "max_tokens"):
                # Emit any final text
                for block in response.content:
                    if block.type == "text" and block.text:
                        await self.emit({"type": "step", "message": block.text})
                break

            if stop_reason == "pause_turn":
                self.messages.append({"role": "assistant", "content": response.content})
                self.messages.append({"role": "user", "content": []})
                continue

            if stop_reason != "tool_use":
                break

            # Process tool calls
            self.messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                await self.emit({"type": "tool_call", "tool": block.name, "input": block.input})

                result = await asyncio.get_running_loop().run_in_executor(
                    None, execute_tool, block.name, block.input, self.repo_path
                )

                if block.name == "write_file":
                    path = block.input.get("path", "")
                    self.modified_files.add(path)
                    await self.emit({"type": "file_written", "path": path})

                # Truncate for SSE display but send full to model
                display = result if len(result) <= 500 else result[:500] + "…"
                await self.emit({"type": "tool_result", "tool": block.name, "content": display})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            self.messages.append({"role": "user", "content": tool_results})
            self.iterations += 1

        if self.iterations >= self.max_iterations:
            await self.emit({"type": "step", "message": f"Reached iteration limit ({self.max_iterations}). Stopping."})

    async def _call_claude(self):
        async with self.client.beta.messages.stream(
            model="claude-fable-5",
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=self.messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "high"},
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
        ) as stream:
            return await stream.get_final_message()
