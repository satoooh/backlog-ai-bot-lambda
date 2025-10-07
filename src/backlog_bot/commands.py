"""
Command parsing, mention detection, and rendering utilities.
"""

from __future__ import annotations

import re
from typing import Any

CMD_RE = re.compile(r"/(summary|ask|update)\b(?P<args>.*)", re.IGNORECASE | re.DOTALL)


def is_bot_mentioned(comment: dict[str, Any], bot_user_id: int) -> bool:
    for notif in comment.get("notifications") or []:
        user = notif.get("user") or {}
        try:
            if int(user.get("id", -1)) == bot_user_id:
                return True
        except Exception:
            continue
    return False


def parse_command(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    m = CMD_RE.search(text)
    if not m:
        return None
    cmd = m.group(1).lower()
    args = (m.group("args") or "").strip()
    if cmd == "ask":
        question = args.strip()
        return {"cmd": "ask", "question": question}
    # summary / update は追加フラグを受け付けず、無視する
    return {"cmd": cmd}


def extract_issue_key(issue: dict[str, Any]) -> str:
    # Backlog payloads typically include both id and issueKey in webhook
    key = issue.get("issueKey") or issue.get("key")
    if isinstance(key, str) and key:
        return key
    # Fallback to numeric id as string
    return str(issue.get("id") or "")


def render_sections(sections: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for title, body in sections:
        if not body:
            continue
        parts.append(f"**{title}**")
        parts.append(body.strip())
        parts.append("")
    return "\n".join(p for p in parts if p).strip()


def rule_based_summary(
    title: str | None,
    description: str | None,
    latest_comments: list[str],
) -> str:
    """Minimal fallback summary without LLM."""
    bullets: list[str] = []
    if title:
        bullets.append(f"題名: {title.strip()}")
    if description:
        bullets.append("説明: " + _shorten(description, 160))
    if latest_comments:
        bullets.append("直近コメント: " + _shorten(latest_comments[0], 160))
    summary = "\n- ".join(["- "] + bullets)
    return render_sections([("要約", summary)])


def _shorten(s: str, n: int) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
