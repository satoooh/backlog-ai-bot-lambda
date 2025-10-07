"""
AWS Lambda handler for Backlog Webhook (comment added) -> Bot reply.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from . import commands
from .backlog import BacklogClient
from .config import Settings, load_settings
from .context_fetch import (
    allowlisted,
    backlog_issue_to_text,
    backlog_wiki_to_text,
    extract_context_urls,
    parse_backlog_issue_url,
    parse_backlog_wiki_url,
)
from .idempotency import s3_record_if_new
from .llm import answer, review_update, summarize

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _rid(context: Any) -> str | None:
    try:
        return getattr(context, "aws_request_id", None)
    except Exception:
        return None


def _log(msg: str, **fields: Any) -> None:
    try:
        rec = {"msg": msg, **fields}
        logger.info(json.dumps(rec, ensure_ascii=False))
    except Exception:
        # Fallback to plain log
        logger.info("%s | %s", msg, fields)


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _get_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body or b"")
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    try:
        return json.loads(body or "{}")
    except Exception:
        return {}


def _get_header(event: dict[str, Any], name: str) -> str | None:
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def _get_query_param(event: dict[str, Any], name: str) -> str | None:
    qs = event.get("queryStringParameters") or {}
    if isinstance(qs, dict):
        val = qs.get(name)
        if val is not None:
            return val
    # Fallback to rawQueryString parsing (API variations)
    raw = event.get("rawQueryString") or ""
    if not raw:
        return None
    for part in raw.split("&"):
        if not part:
            continue
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
    return None


def _load_secrets(_: Settings) -> dict[str, str]:
    import os

    api_key = os.getenv("BACKLOG_API_KEY")
    return {"BACKLOG_API_KEY": api_key} if api_key else {}


def _extract_comment_and_issue(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    comment = payload.get("comment") or {}
    issue = payload.get("issue") or {}
    return comment, issue


def lambda_handler(
    event: dict[str, Any], context: Any
) -> dict[str, Any]:  # pragma: no cover - wrapper
    settings = load_settings()
    start_ts = time.time()

    # 1) Verify webhook secret quickly
    #    Accept either header `X-Webhook-Secret` or query `?token=` (Function URL)
    if settings.webhook_shared_secret:
        supplied = _get_header(event, "X-Webhook-Secret") or _get_query_param(event, "token")
        if supplied != settings.webhook_shared_secret:
            _log(
                "auth_failed",
                rid=_rid(context),
                reason="token_mismatch",
            )
            return _response(401, {"error": "unauthorized"})

    # 2) Parse body
    payload = _get_body(event)
    comment, issue = _extract_comment_and_issue(payload)
    if not comment or not issue:
        _log("ignored_no_comment_or_issue", rid=_rid(context))
        return _response(200, {"result": "ignored"})

    # 3) Mention + command detection
    #    require_mention=True の場合は @BOT のメンション必須。
    #    False の場合はメンション不要だが、必要に応じて投稿者の許可リストで制限。
    if settings.require_mention:
        if settings.bot_user_id and not commands.is_bot_mentioned(comment, settings.bot_user_id):
            _log(
                "ignored_no_mention",
                rid=_rid(context),
                issueKey=issue.get("issueKey") or issue.get("key") or issue.get("id"),
                commentId=comment.get("id"),
            )
            return _response(200, {"result": "ignored"})
    else:
        author_id = None
        try:
            author_id = int((comment.get("createdUser") or {}).get("id", -1))
        except Exception:
            author_id = None
        if settings.allowed_trigger_user_ids and (
            author_id not in settings.allowed_trigger_user_ids
        ):
            _log(
                "ignored_author_not_allowed",
                rid=_rid(context),
                authorId=author_id,
            )
            return _response(200, {"result": "ignored"})

    cmd = commands.parse_command(comment.get("content"))
    if not cmd:
        _log("ignored_no_command", rid=_rid(context))
        return _response(200, {"result": "ignored"})

    issue_key = commands.extract_issue_key(issue)
    comment_id = str(comment.get("id") or "")

    # 4) Idempotency
    if settings.idempotency_bucket:
        marker = f"{issue_key}/{comment_id}"
        if not s3_record_if_new(settings.idempotency_bucket, marker):
            _log(
                "duplicate_ignored",
                rid=_rid(context),
                issueKey=issue_key,
                commentId=comment_id,
            )
            return _response(200, {"result": "duplicate_ignored"})

    # 5) Backlog API client
    secrets = _load_secrets(settings)
    api_key = secrets.get("BACKLOG_API_KEY")
    if not api_key:
        _log("config_error_missing_api_key", rid=_rid(context))
        return _response(500, {"error": "BACKLOG_API_KEY not found"})
    bl = BacklogClient(settings.backlog_base_url, api_key)

    # 6) Fetch issue + recent comments
    try:
        t0 = time.time()
        issue_obj = bl.get_issue(issue_key)
        recent = bl.list_comments(issue_key, count=settings.recent_comment_count)
        _log(
            "backlog_fetch_ok",
            rid=_rid(context),
            issueKey=issue_key,
            comments=len(recent),
            ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:  # pragma: no cover
        logger.exception("Backlog fetch failed")
        _log(
            "backlog_fetch_error",
            rid=_rid(context),
            issueKey=issue_key,
            error=str(e),
        )
        return _response(500, {"error": f"backlog fetch failed: {e}"})

    title = issue_obj.get("summary") or issue_obj.get("title") or ""
    description = issue_obj.get("description") or ""
    latest_texts = [str((c.get("content") or "").strip()) for c in recent if c.get("content")]

    # 7) Optional link context
    used_context_urls: list[str] = []
    context_texts: list[str] = []
    for url in extract_context_urls(comment.get("content")):
        if not allowlisted(url, settings.context_allowed_hosts):
            continue
        if sum(len(t) for t in context_texts) >= settings.context_total_max_bytes:
            break
        try:
            ctx_issue_key, comment_ref = parse_backlog_issue_url(url, settings.backlog_base_url)
            wiki_id = parse_backlog_wiki_url(url, settings.backlog_base_url)
            if ctx_issue_key:
                issue_obj2 = bl.get_issue(ctx_issue_key)
                comments2 = bl.list_comments(issue_key, count=settings.recent_comment_count)
                txt = backlog_issue_to_text(
                    issue_obj2, comments2, settings.context_url_max_bytes, comment_ref
                )
                _log(
                    "context_added_issue",
                    rid=_rid(context),
                    source=url,
                    issueKey=ctx_issue_key,
                )
            elif wiki_id:
                wiki = bl.get_wiki(int(wiki_id))
                w_attachments = bl.list_wiki_attachments(int(wiki_id))
                txt = backlog_wiki_to_text(wiki, w_attachments, settings.context_url_max_bytes)
                _log(
                    "context_added_wiki",
                    rid=_rid(context),
                    source=url,
                    wikiId=int(wiki_id),
                )
            else:
                # 非Backlog URLは無視
                continue
        except Exception:
            _log("context_fetch_error", rid=_rid(context), source=url)
            continue
        if txt:
            context_texts.append(txt)
            used_context_urls.append(url)

    # 8) Build prompts per command + retry LLM, no rule-based fallback
    model_id = settings.llm_model
    reply_text = ""

    def _build_summary_prompt() -> str:
        p = (
            f"チケットの題名と説明、直近コメントからPM観点の要約を作ってください。\n"
            f"題名: {title}\n説明: {description[:1500]}\n"
            f"直近コメント(新しい順に最大10):\n- " + "\n- ".join(latest_texts[:10])
        )
        if context_texts:
            p += "\n\n追加コンテキスト:\n" + "\n".join(context_texts[:2])
        return p

    def _build_ask_prompt(q: str) -> str:
        p = (
            f"以下のチケット情報に基づいて質問に回答してください。\n質問: {q}\n\n"
            f"題名: {title}\n説明: {description[:1500]}\n"
            f"直近コメント(新しい順に最大10):\n- " + "\n- ".join(latest_texts[:10])
        )
        if context_texts:
            p += "\n\n追加コンテキスト:\n" + "\n".join(context_texts[:2])
        return p

    def _build_update_prompt() -> str:
        return (
            "以下の本文から、期限・優先度・状態・担当の妥当性をレビューし、"
            "フォーマット『項目名: before → after （理由）』で更新提案を出してください。\n\n"
            f"題名: {title}\n説明: {description[:1500]}\n"
            f"直近コメント(新しい順に最大10):\n- " + "\n- ".join(latest_texts[:10])
        )

    def _call_with_retry(kind: str) -> str:
        last_err: Exception | None = None
        for _i in range(max(1, settings.llm_max_retries)):
            try:
                if kind == "summary":
                    prompt = _build_summary_prompt()
                    t0 = time.time()
                    out = summarize(model_id, prompt)
                    _log(
                        "llm_ok",
                        rid=_rid(context),
                        kind=kind,
                        model=model_id,
                        ms=int((time.time() - t0) * 1000),
                        prompt_chars=len(prompt),
                        out_chars=len(out or ""),
                    )
                    return out
                if kind == "ask":
                    q = cmd.get("question", "").strip()
                    prompt = _build_ask_prompt(q)
                    t0 = time.time()
                    out = answer(model_id, prompt)
                    _log(
                        "llm_ok",
                        rid=_rid(context),
                        kind=kind,
                        model=model_id,
                        ms=int((time.time() - t0) * 1000),
                        prompt_chars=len(prompt),
                        out_chars=len(out or ""),
                    )
                    return out
                if kind == "update":
                    prompt = _build_update_prompt()
                    t0 = time.time()
                    out = review_update(model_id, prompt)
                    _log(
                        "llm_ok",
                        rid=_rid(context),
                        kind=kind,
                        model=model_id,
                        ms=int((time.time() - t0) * 1000),
                        prompt_chars=len(prompt),
                        out_chars=len(out or ""),
                    )
                    return out
                raise ValueError("unknown kind")
            except Exception as e:  # pragma: no cover
                last_err = e
                _log(
                    "llm_retry",
                    rid=_rid(context),
                    kind=kind,
                    model=model_id,
                    error=str(e),
                )
        raise last_err or RuntimeError("LLM call failed")

    try:
        reply_text = _call_with_retry(cmd["cmd"])
        if cmd["cmd"] == "summary" and used_context_urls:
            ctx_lines = "\n".join(f"- {u}" for u in used_context_urls)
            reply_text += "\n\n**参照コンテキスト**\n" + ctx_lines
    except Exception as e:  # pragma: no cover
        logger.exception("LLM failed after retries: %s", e)
        _log("llm_failed", rid=_rid(context), error=str(e))
        error_text = (
            "⚠️ エラーが発生したため要約/回答を生成できませんでした。"
            "お手数ですが管理者にお問い合わせください。"
        )
        try:
            bl.post_comment(issue_key, error_text)
        except Exception:
            pass
        return _response(500, {"error": "llm_failed"})

    # 9) Post reply
    try:
        bl.post_comment(issue_key, reply_text)
    except Exception as e:  # pragma: no cover
        logger.exception("Backlog post failed")
        _log("backlog_post_error", rid=_rid(context), error=str(e))
        return _response(500, {"error": f"backlog post failed: {e}"})
    _log(
        "ok",
        rid=_rid(context),
        issueKey=issue_key,
        commentId=comment_id,
        ms_total=int((time.time() - start_ts) * 1000),
        cmd=cmd.get("cmd"),
    )
    return _response(200, {"result": "ok"})
