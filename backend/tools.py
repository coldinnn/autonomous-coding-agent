import os
import subprocess
from pathlib import Path

COMMAND_ALLOWLIST = {
    "pytest", "python", "python3", "pip",
    "git", "grep", "find", "ls", "cat",
    "rg", "npm", "node", "go", "make", "cargo", "yarn",
}

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the repo root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories at a given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to repo root. Use '.' for root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in the repository using grep/ripgrep.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex or literal string to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in. Defaults to '.' (entire repo).",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to limit which files are searched (e.g. '*.py').",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to repo root.",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": "Run an allowed shell command in the repo directory. Allowed commands: pytest, python, python3, pip, git, grep, find, ls, cat, rg, npm, node, go, make, cargo, yarn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command and arguments as a list, e.g. ['pytest', 'tests/', '-v'].",
                }
            },
            "required": ["command"],
        },
    },
]


def execute_tool(name: str, inputs: dict, repo_path: str) -> str:
    try:
        if name == "read_file":
            return _read_file(inputs["path"], repo_path)
        elif name == "list_directory":
            return _list_directory(inputs["path"], repo_path)
        elif name == "search_code":
            return _search_code(inputs, repo_path)
        elif name == "write_file":
            return _write_file(inputs["path"], inputs["content"], repo_path)
        elif name == "run_command":
            return _run_command(inputs["command"], repo_path)
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e}"


def _read_file(path: str, repo_path: str) -> str:
    full = Path(repo_path) / path
    if not full.resolve().is_relative_to(Path(repo_path).resolve()):
        return "Error: path traversal not allowed"
    if not full.exists():
        return f"File not found: {path}"
    content = full.read_text(errors="replace")
    # Cap at 8000 chars to avoid blowing context
    if len(content) > 8000:
        content = content[:8000] + f"\n\n[... truncated — file is {len(full.read_bytes())} bytes total]"
    return content


def _list_directory(path: str, repo_path: str) -> str:
    full = Path(repo_path) / path
    if not full.resolve().is_relative_to(Path(repo_path).resolve()):
        return "Error: path traversal not allowed"
    if not full.exists():
        return f"Directory not found: {path}"
    entries = []
    for item in sorted(full.iterdir()):
        if item.name.startswith(".git"):
            continue
        suffix = "/" if item.is_dir() else ""
        entries.append(f"{item.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


def _search_code(inputs: dict, repo_path: str) -> str:
    pattern = inputs["pattern"]
    search_path = inputs.get("path", ".")
    file_pattern = inputs.get("file_pattern")

    # prefer rg, fall back to grep
    try:
        cmd = ["rg", "--line-number", "--no-heading", "-m", "50"]
        if file_pattern:
            cmd += ["--glob", file_pattern]
        cmd += [pattern, search_path]
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        output = result.stdout or result.stderr
    except FileNotFoundError:
        cmd = ["grep", "-rn", "--include", file_pattern or "*", pattern, search_path]
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        output = result.stdout or result.stderr

    if not output.strip():
        return "No matches found."
    lines = output.strip().splitlines()
    if len(lines) > 100:
        lines = lines[:100]
        lines.append("... (truncated to 100 lines)")
    return "\n".join(lines)


def _write_file(path: str, content: str, repo_path: str) -> str:
    full = Path(repo_path) / path
    if not full.resolve().is_relative_to(Path(repo_path).resolve()):
        return "Error: path traversal not allowed"
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return f"Written {len(content)} bytes to {path}"


def _run_command(command: list, repo_path: str) -> str:
    if not command:
        return "Error: empty command"
    binary = os.path.basename(command[0])
    if binary not in COMMAND_ALLOWLIST:
        return f"Error: '{binary}' is not in the allowed command list: {sorted(COMMAND_ALLOWLIST)}"
    result = subprocess.run(
        command,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    if len(output) > 6000:
        output = output[:6000] + "\n... (truncated)"
    return output or "(no output)"
