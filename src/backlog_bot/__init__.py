"""
Backlog AI Bot (Lambda + Bedrock Claude)

Where: AWS Lambda via Function URL (Backlog Webhook target).
What:  Parse @mention + command, fetch issue/comments, call Bedrock Claude, post reply.
Why:   Minimal, RAG-less summarizer/QA/update helper for Backlog.
"""

__all__ = [
    "config",
    "handler",
    "backlog",
    "commands",
    "context_fetch",
    "idempotency",
    "llm",
]
