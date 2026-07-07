import asyncio
import json
import os
import shutil
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import CodingAgent
from github_ops import (
    clone_repo,
    commit_and_push,
    fetch_issue,
    make_branch_name,
    make_temp_dir,
    open_draft_pr,
    parse_issue_url,
)

load_dotenv()

app = FastAPI(title="Autonomous Coding Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(FRONTEND_DIR, "index.html")) as f:
        return f.read()


@app.get("/run")
async def run_agent(issue_url: str = Query(..., description="GitHub issue URL")):
    return StreamingResponse(
        _agent_stream(issue_url),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _agent_stream(issue_url: str) -> AsyncIterator[str]:
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def producer():
        repo_path = None
        try:
            await emit({"type": "step", "message": f"Fetching issue from {issue_url}..."})
            repo, issue_number = parse_issue_url(issue_url)
            issue = fetch_issue(repo, issue_number)
            await emit({"type": "issue", "title": issue["title"], "body": issue.get("body", "")})

            repo_path = make_temp_dir()
            await emit({"type": "step", "message": f"Cloning {repo}..."})
            clone_repo(repo, repo_path)

            branch_name = make_branch_name(issue_number, issue["title"])
            from github_ops import create_branch
            create_branch(repo_path, branch_name)
            await emit({"type": "step", "message": f"Working on branch: {branch_name}"})

            agent = CodingAgent(issue=issue, repo_path=repo_path, emit=emit)
            await agent.run()

            if agent.modified_files:
                await emit({"type": "step", "message": "Committing changes and pushing..."})
                pushed = commit_and_push(repo_path, branch_name, issue_number, agent.modified_files)
                if pushed:
                    await emit({"type": "step", "message": "Opening draft PR..."})
                    pr_url = open_draft_pr(repo, branch_name, issue)
                    await emit({"type": "pr_opened", "url": pr_url})
                    await emit({"type": "done", "message": f"Done! Draft PR: {pr_url}"})
                else:
                    await emit({"type": "done", "message": "No changes were made to commit."})
            else:
                await emit({"type": "done", "message": "Agent finished without modifying any files."})

        except Exception as exc:
            await emit({"type": "error", "message": str(exc)})
        finally:
            if repo_path and os.path.exists(repo_path):
                shutil.rmtree(repo_path, ignore_errors=True)
            await queue.put(sentinel)

    task = asyncio.create_task(producer())

    while True:
        item = await queue.get()
        if item is sentinel:
            break
        yield f"data: {json.dumps(item)}\n\n"

    await task
