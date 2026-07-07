# Autonomous Coding Agent

An autonomous agent that reads a GitHub issue, clones the repo, writes a fix, runs tests, and opens a draft PR — powered by Claude Fable 5 with extended thinking.

## Architecture

```
frontend/index.html          # Live terminal dashboard (SSE)
backend/
  main.py                    # FastAPI + SSE endpoint
  agent.py                   # Fable 5 agentic tool loop
  tools.py                   # 5 tools: read/list/search/write/run
  github_ops.py              # GitHub API + git subprocess ops
```

**Flow:** issue URL → fetch issue → clone repo → create branch → Fable 5 tool loop (explore → read → write → test → iterate) → commit → push → open draft PR

## Setup

```bash
cd backend
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and GITHUB_TOKEN in .env

python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
../.venv/bin/uvicorn main:app --reload --port 8124
```

Open `http://localhost:8124`, paste a GitHub issue URL, click **Run Agent**.

## What the agent can do

- Explores repo structure and finds relevant files
- Reads code carefully before writing
- Makes surgical, minimal changes
- Runs `pytest` (or whatever test command fits the repo) to verify
- Iterates up to 5 fix attempts before stopping
- Caps at 30 total tool calls to bound cost

## Limits / scope

- Best on Python repos with `pytest`
- Single-file or few-file changes
- Requires the GitHub token to have `repo` write scope for push + PR creation
- Fable 5 thinking is streamed live to the dashboard via SSE

## Tech

- Claude Fable 5 (`claude-fable-5`) with `output_config.effort=high` and server-side Opus 4.8 fallback
- FastAPI + `StreamingResponse` for SSE
- httpx for GitHub REST API
- subprocess for git and test running
