"""
Configuration helpers and defaults.

Centralize tunables to avoid magic numbers in code/tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None else default


@dataclass(frozen=True)
class Settings:
    backlog_base_url: str
    backlog_space: str | None
    bot_user_id: int
    webhook_shared_secret: str | None
    secrets_llm_name: str | None
    idempotency_bucket: str | None
    recent_comment_count: int
    context_url_max_bytes: int
    context_total_max_bytes: int
    context_allowed_hosts: tuple[str, ...]
    llm_provider: str
    llm_model: str
    llm_timeout_seconds: int
    llm_max_retries: int
    require_mention: bool
    allowed_trigger_user_ids: tuple[int, ...]


def load_settings() -> Settings:
    """Load settings from environment with safe defaults for local tests."""

    space = _env("BACKLOG_SPACE")
    base_url = _env("BACKLOG_BASE_URL") or (
        f"https://{space}.backlog.com" if space else "https://example.backlog.com"
    )

    bot_user_id = int(_env("BOT_USER_ID", "0") or 0)

    allowed_hosts = tuple(
        h.strip() for h in ((_env("CONTEXT_ALLOWED_HOSTS", "") or "").split(",")) if h.strip()
    )

    return Settings(
        backlog_base_url=base_url,
        backlog_space=space,
        bot_user_id=bot_user_id,
        webhook_shared_secret=_env("WEBHOOK_SHARED_SECRET"),
        secrets_llm_name=_env("LLM_SECRET_NAME"),
        idempotency_bucket=_env("IDEMPOTENCY_BUCKET"),
        recent_comment_count=int(_env("RECENT_COMMENT_COUNT", "50") or 50),
        context_url_max_bytes=int(_env("CONTEXT_URL_MAX_BYTES", "100000") or 100000),
        context_total_max_bytes=int(_env("CONTEXT_TOTAL_MAX_BYTES", "200000") or 200000),
        context_allowed_hosts=allowed_hosts,
        llm_provider=_env("LLM_PROVIDER", "bedrock") or "bedrock",
        llm_model=_env("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
        or "anthropic.claude-3-haiku-20240307-v1:0",
        llm_timeout_seconds=int(_env("LLM_TIMEOUT_SECONDS", "10") or 10),
        llm_max_retries=int(_env("LLM_MAX_RETRIES", "2") or 2),
        require_mention=(
            (_env("REQUIRE_MENTION", "true") or "true").lower() in ("1", "true", "yes")
        ),
        allowed_trigger_user_ids=tuple(
            int(x)
            for x in [
                s.strip()
                for s in ((_env("ALLOWED_TRIGGER_USER_IDS", "") or "").split(","))
                if s.strip()
            ]
        ),
    )
