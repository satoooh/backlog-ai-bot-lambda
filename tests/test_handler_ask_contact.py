import json

import backlog_bot.handler as h


class FakeS3:
    def __init__(self):
        self.store = set()

    def head_object(self, Bucket: str, Key: str):
        if (Bucket, Key) not in self.store:
            raise Exception("404")
        return {}

    def put_object(self, Bucket: str, Key: str, Body: bytes):
        self.store.add((Bucket, Key))
        return {}


class FakeBacklog:
    def __init__(self, *_a, **_k):
        self.posted = []

    def get_issue(self, issue_id_or_key: str):
        return {
            "summary": "S",
            "description": "D",
            "assignee": {"id": 10, "name": "Alice"},
            "createdUser": {"id": 1, "name": "Reporter"},
        }

    def list_comments(self, issue_id_or_key: str, count: int = 30):
        return [
            {"content": "c1", "createdUser": {"id": 20, "name": "Bob"}},
            {"content": "c2", "createdUser": {"id": 20, "name": "Bob"}},
            {"content": "c3", "createdUser": {"id": 30, "name": "Carol"}},
        ]

    def post_comment(self, issue_id_or_key: str, content: str):
        self.posted.append(content)
        return {"ok": True}


def test_ask_suggest_contacts_on_insufficient_answer(monkeypatch):
    import backlog_bot.idempotency as idem
    import backlog_bot.llm as llm

    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "secret")
    monkeypatch.setenv("IDEMPOTENCY_BUCKET", "b")
    monkeypatch.setenv("BACKLOG_SPACE", "space")
    monkeypatch.setenv("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("BOT_USER_ID", "999")
    monkeypatch.setenv("BACKLOG_API_KEY", "x")

    fs3 = FakeS3()
    fb = FakeBacklog()

    class BR:
        def invoke_model(self, **_kw):
            # Force an "insufficient" style answer in Japanese
            text = "提供情報では特定できません。情報が不足しています。"
            body = json.dumps({"content": [{"text": text}]})
            class R:
                def read(self):
                    return body.encode("utf-8")
            return {"body": R()}

    class BotoModule:
        def client(self, name: str):
            if name == "s3":
                return fs3
            if name == "bedrock-runtime":
                return BR()
            raise ValueError(name)

    monkeypatch.setitem(idem.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(llm.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(h.__dict__, "BacklogClient", lambda *_a, **_k: fb)

    body = {
        "comment": {
            "id": 3000,
            "content": "@bot /ask だれが対応すべき？",
            "notifications": [{"user": {"id": 999}}],
        },
        "issue": {"issueKey": "PROJ-4", "id": 4},
    }
    event = {
        "headers": {"X-Webhook-Secret": "secret"},
        "body": json.dumps(body, ensure_ascii=False),
        "isBase64Encoded": False,
    }

    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # LLMの出力そのままを投稿（ロジックでの候補付記はしない）
    posted = "\n".join(fb.posted)
    assert "情報が不足" in posted
