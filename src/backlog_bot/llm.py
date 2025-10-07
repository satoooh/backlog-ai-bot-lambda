"""
Bedrock Claude minimal wrapper.

Uses Anthropic Messages API on Bedrock (anthropic_version=bedrock-2023-05-31).
"""

from __future__ import annotations

import importlib
import json


def _boto3():
    # Allow tests to monkeypatch module-level `boto3` symbol.
    return globals().get("boto3") or importlib.import_module("boto3")


def _bedrock_client():
    return _boto3().client("bedrock-runtime")


def _invoke_messages(
    model_id: str, system: str | None, user_text: str, max_tokens: int = 512
) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
    }
    if system:
        body["system"] = system
    client = _bedrock_client()
    resp = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    data = json.loads(resp["body"].read())
    # Anthropic messages returns { content: [{text: "..."}]} on Bedrock
    return data.get("content", [{}])[0].get("text", "")


def summarize(model_id: str, prompt: str) -> str:
    system = (
        "あなたはプロジェクトマネジメント観点の要約を作るアシスタントです。"
        "出力は日本語、Markdown。次を短く整理: 1) 背景/目的 2) 現状と進捗"
        " 3) 期限と担当 4) リスク/ブロッカー 5) 次の具体アクション(1-3)。"
        " 最後に『不足情報/確認事項』を箇条書きで質問として提示してください。"
    )
    return _invoke_messages(model_id, system, prompt, max_tokens=700)


def answer(model_id: str, prompt: str) -> str:
    system = (
        "あなたはBacklogチケットのコンテキストに基づいて正確に回答するAIです。"
        "不確実な点はその旨を明記し、根拠を短く示してください。"
    )
    return _invoke_messages(model_id, system, prompt, max_tokens=700)


def review_update(model_id: str, prompt: str) -> str:
    system = (
        "あなたはBacklogチケットのフィールド整合性レビューを行います。"
        "出力は日本語、Markdownの箇条書き。フォーマットは厳守:"
        "『項目名: before → after （理由）』を各行で出力。"
        " 項目名の例: 期限, 優先度, 状態, 担当者, カスタム(… )。"
        " 変更不要なら提案しないか、'変更なし'と明記。"
    )
    return _invoke_messages(model_id, system, prompt, max_tokens=700)
