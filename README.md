# Autonomous Coding Agent

An autonomous agent that reads a GitHub issue, clones the repo, explores the codebase, writes a fix, runs tests, and opens a draft PR — end to end, no human in the loop.

Powered by **Claude Fable 5** with extended thinking, streamed live to a terminal-aesthetic dashboard over SSE.

![Model](https://img.shields.io/badge/model-claude--fable--5-6c63ff)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20SSE-00d4ff)
![Tools](https://img.shields.io/badge/tools-5-00ff88)

**Live proof:** [coldinnn/claude-cost-analyzer#2](https://github.com/coldinnn/claude-cost-analyzer/pull/2) — the agent found a real bug, read the source, wrote the fix, verified it with a smoke test, and opened this draft PR autonomously.

---

## What it does

1. Fetches the issue from GitHub's REST API
2. Clones the repo (`--depth 50`) to a temp directory
3. Creates a fix branch (`fix/issue-N-slug`)
4. Runs a Fable 5 agentic loop: explore → read → write → test → iterate
5. Commits the changes, pushes the branch, opens a draft PR
6. Streams every step — thinking blocks, tool calls, file writes — live to the browser

---

## Architecture

```
Browser (EventSource)
    │
    └── GET /run?issue_url=...
            │
            ▼
    FastAPI StreamingResponse (text/event-stream)
            │
            ├── github_ops.py  ── fetch issue, clone, branch, push, PR
            │
            └── agent.py  ── Fable 5 agentic loop
                    │
                    ├── list_directory   explore repo layout
                    ├── read_file        read source files
                    ├── search_code      grep/ripgrep for symbols
                    ├── write_file       apply fix (full file content)
                    └── run_command      run tests / smoke checks
                            │
                            └── allowlist: pytest python3 git grep
                                         find rg npm node go make cargo
```

---

## Agent loop (simplified)

```python
while iterations < 30:
    response = await client.beta.messages.stream(
        model="claude-fable-5",
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-06-01"],
        fallbacks=[{"model": "claude-opus-4-8"}],
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )

    if stop_reason == "tool_use":   # execute tools, continue
    if stop_reason == "pause_turn": # Fable 5 mid-stream pause, resume
    if stop_reason == "refusal":    # safety filter — Opus 4.8 fallback kicks in
    if stop_reason == "end_turn":   # done
```

Key Fable 5 details: thinking is always on (omit the param or pass `adaptive`). `pause_turn` means the model paused mid-agentic-loop — append the turn and re-call. The server-side fallback transparently re-runs declined requests on Opus 4.8 within the same API call.

---

## SSE event stream

Every action emits a typed JSON event:

```
data: {"type": "step",         "message": "Cloning repo..."}
data: {"type": "issue",        "title": "...", "body": "..."}
data: {"type": "thinking",     "text": "I should read models.py first..."}
data: {"type": "tool_call",    "tool": "read_file", "input": {"path": "models.py"}}
data: {"type": "tool_result",  "tool": "read_file", "content": "..."}
data: {"type": "file_written", "path": "models.py"}
data: {"type": "pr_opened",    "url": "https://github.com/..."}
data: {"type": "done",         "message": "Done! Draft PR: ..."}
```

---

## Setup

```bash
git clone https://github.com/coldinnn/autonomous-coding-agent
cd autonomous-coding-agent/backend

python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# ANTHROPIC_API_KEY=sk-ant-...
# GITHUB_TOKEN=ghp_...  (needs repo scope: push + pull_request)

uvicorn main:app --reload --port 8124
```

Open `http://localhost:8124`, paste a GitHub issue URL, click **Run Agent**.

---

## Scope and limits

- Best on Python repos with `pytest`
- Handles single-file or few-file changes well
- Max 5 fix attempts, 30 total tool calls — bounds cost and runtime
- GitHub token needs `repo` write scope for push and PR creation
- Temp repo is deleted after each run

---

## Stack

| | |
|---|---|
| Model | `claude-fable-5` — extended thinking, agentic tool loop |
| Fallback | Server-side Opus 4.8 on safety filter |
| Backend | FastAPI + `StreamingResponse` (`text/event-stream`) |
| GitHub | httpx → GitHub REST API v3 |
| Git ops | `subprocess` — clone, branch, commit, push |
| Test runner | `subprocess` — allowlisted commands, 60s timeout |
| Frontend | Single `index.html`, vanilla JS `EventSource` |
