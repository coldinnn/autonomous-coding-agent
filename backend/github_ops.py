import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def parse_issue_url(url: str) -> tuple[str, int]:
    """Return (owner/repo, issue_number) from a GitHub issue URL."""
    match = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", url)
    if not match:
        raise ValueError(f"Cannot parse GitHub issue URL: {url}")
    return match.group(1), int(match.group(2))


def fetch_issue(repo: str, issue_number: int) -> dict:
    headers = _auth_headers()
    r = httpx.get(f"{GITHUB_API}/repos/{repo}/issues/{issue_number}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def clone_repo(repo: str, target_dir: str) -> None:
    clone_url = f"https://{GITHUB_TOKEN}@github.com/{repo}.git"
    subprocess.run(
        ["git", "clone", "--depth", "50", clone_url, target_dir],
        check=True,
        capture_output=True,
        text=True,
    )
    # Configure git identity for commits
    subprocess.run(
        ["git", "config", "user.email", "agent@autonomous-coder.local"],
        cwd=target_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Autonomous Coding Agent"],
        cwd=target_dir, check=True, capture_output=True,
    )


def create_branch(repo_path: str, branch_name: str) -> None:
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )


def commit_and_push(repo_path: str, branch_name: str, issue_number: int, modified_files: set) -> bool:
    """Stage modified files, commit, and push. Returns True if anything was pushed."""
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path, capture_output=True, text=True,
    )
    if not status.stdout.strip():
        return False

    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"fix: resolve issue #{issue_number}\n\nAutomated fix by autonomous-coding-agent."],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "push", "origin", branch_name],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )
    return True


def open_draft_pr(repo: str, branch_name: str, issue: dict) -> str:
    """Open a draft PR and return its URL."""
    headers = _auth_headers()
    default_branch = _get_default_branch(repo)
    body = (
        f"Closes #{issue['number']}\n\n"
        f"**Original issue:** {issue['title']}\n\n"
        f"---\n"
        f"_This PR was created automatically by the autonomous coding agent._"
    )
    payload = {
        "title": f"fix: {issue['title']} (#{issue['number']})",
        "body": body,
        "head": branch_name,
        "base": default_branch,
        "draft": True,
    }
    r = httpx.post(f"{GITHUB_API}/repos/{repo}/pulls", json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["html_url"]


def _get_default_branch(repo: str) -> str:
    headers = _auth_headers()
    r = httpx.get(f"{GITHUB_API}/repos/{repo}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("default_branch", "main")


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def make_branch_name(issue_number: int, issue_title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")[:50]
    return f"fix/issue-{issue_number}-{slug}"


def make_temp_dir() -> str:
    return tempfile.mkdtemp(prefix="agent-repo-")
