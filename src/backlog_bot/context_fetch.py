"""
Extract additional context for prompts.

- Backlog issue URLs: APIから課題とコメントを取得してテキスト化（推奨）
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any


def extract_context_urls(text: str | None) -> list[str]:
    if not text:
        return []
    for line in reversed(text.splitlines()):
        if line.strip().lower().startswith("context:"):
            parts = line.split(":", 1)[1].strip().split()
            return [p for p in parts if is_http_url(p)]
    return []


def is_http_url(s: str) -> bool:
    try:
        u = urllib.parse.urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def allowlisted(url: str, allowed_hosts: Iterable[str]) -> bool:
    if not allowed_hosts:
        return True
    host = urllib.parse.urlparse(url).netloc
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


# ---------- Backlog-specific helpers ----------


def parse_backlog_issue_url(url: str, backlog_base_url: str) -> tuple[str | None, int | None]:
    """Return (issueKey, commentId) if url is a Backlog issue view URL, else (None, None).

    Accepts formats like:
      https://{space}.backlog.com/view/PROJ-123
      https://{space}.backlog.com/view/PROJ-123#comment-456
    """
    try:
        u = urllib.parse.urlparse(url)
        base = urllib.parse.urlparse(backlog_base_url)
        if u.netloc != base.netloc:
            return (None, None)
        if not u.path.startswith("/view/"):
            return (None, None)
        issue_key = u.path.split("/view/")[-1].strip()
        comment_id: int | None = None
        if u.fragment.startswith("comment-"):
            try:
                comment_id = int(u.fragment.split("-", 1)[1])
            except Exception:
                comment_id = None
        return (issue_key, comment_id)
    except Exception:
        return (None, None)


def backlog_issue_to_text(
    issue: dict[str, Any],
    comments: list[dict[str, Any]],
    max_chars: int,
    only_comment_id: int | None = None,
) -> str:
    """Flatten Backlog issue fields + comments to a compact text for LLM context."""
    parts: list[str] = []
    key = issue.get("issueKey") or issue.get("key") or ""
    title = issue.get("summary") or issue.get("title") or ""
    desc = issue.get("description") or ""

    status = (issue.get("status") or {}).get("name") or ""
    priority = (issue.get("priority") or {}).get("name") or ""
    assignee = (issue.get("assignee") or {}).get("name") or ""
    due = issue.get("dueDate") or ""

    parts.append(f"Backlog Issue {key}")
    if title:
        parts.append(f"題名: {title}")
    if desc:
        parts.append(f"説明: {desc}")
    fields = [
        f"状態: {status}" if status else "",
        f"優先度: {priority}" if priority else "",
        f"担当者: {assignee}" if assignee else "",
        f"期限: {due}" if due else "",
    ]
    fields = [f for f in fields if f]
    if fields:
        parts.append("フィールド: " + ", ".join(fields))

    # Comments
    if comments:
        parts.append("コメント:")
        for c in comments:
            if only_comment_id and int(c.get("id", 0)) != int(only_comment_id):
                continue
            author = (c.get("createdUser") or {}).get("name") or ""
            created = c.get("created") or ""
            content = (c.get("content") or "").strip()
            line = f"- [{created}] {author}: {content}"
            parts.append(line)

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def parse_backlog_wiki_url(url: str, backlog_base_url: str) -> int | None:
    """Return wikiId if url points to a Backlog wiki page.

    Accept typical formats like:
      https://{space}.backlog.com/wiki/12345
      https://{space}.backlog.com/wiki/PROJ/12345  -> use last numeric segment
    If an id cannot be determined, returns None.
    """
    try:
        u = urllib.parse.urlparse(url)
        base = urllib.parse.urlparse(backlog_base_url)
        if u.netloc != base.netloc:
            return None
        if not u.path.startswith("/wiki/"):
            return None
        last = u.path.rstrip("/").split("/")[-1]
        return int(last)
    except Exception:
        return None


def backlog_wiki_to_text(
    wiki: dict[str, Any], attachments: list[dict[str, Any]], max_chars: int
) -> str:
    """Flatten Backlog wiki page to compact text."""
    parts: list[str] = []
    name = wiki.get("name") or wiki.get("title") or ""
    content = wiki.get("content") or wiki.get("body") or ""
    project = (wiki.get("project") or {}).get("projectKey") or wiki.get("projectId") or ""
    created = wiki.get("created") or ""
    updated = wiki.get("updated") or ""
    created_user = (wiki.get("createdUser") or {}).get("name") or ""
    updated_user = (wiki.get("updatedUser") or {}).get("name") or ""

    parts.append("Backlog Wiki")
    if project:
        parts.append(f"プロジェクト: {project}")
    if name:
        parts.append(f"タイトル: {name}")
    if created or created_user:
        parts.append(f"作成: {created} {created_user}".strip())
    if updated or updated_user:
        parts.append(f"更新: {updated} {updated_user}".strip())
    if content:
        parts.append("本文:")
        parts.append(content)
    if attachments:
        parts.append("添付:")
        for a in attachments:
            fname = a.get("name") or a.get("filename") or ""
            size = a.get("size") or a.get("fileSize") or ""
            parts.append(f"- {fname} ({size})".strip())

    text = "\n".join(p for p in parts if p)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text
