import json
import types

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


class FakeBedrock:
    def invoke_model(self, modelId: str, body: str, accept: str, contentType: str):
        # Echo back a minimal messages response
        return {
            "body": types.SimpleNamespace(
                read=lambda: json.dumps({"content": [{"text": "OK"}]}).encode("utf-8")
            )
        }


class FakeSecrets:
    def get_secret_value(self, SecretId: str):
        return {"SecretString": json.dumps({"BACKLOG_API_KEY": "x"})}


class FakeBacklog:
    def __init__(self, *_a, **_k):
        pass

    def get_issue(self, issue_id_or_key: str):
        return {"summary": "S", "description": "D"}

    def list_comments(self, issue_id_or_key: str, count: int = 30):
        return [{"content": "c1"}, {"content": "c2"}]

    def post_comment(self, issue_id_or_key: str, content: str):
        assert "OK" in content or "要約" in content
        return {"ok": True}


def test_lambda_handler_happy_path(monkeypatch):
    # Monkeypatch boto3 clients used in idempotency and llm/secrets
    import backlog_bot.idempotency as idem
    import backlog_bot.llm as llm

    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "secret")
    monkeypatch.setenv("IDEMPOTENCY_BUCKET", "b")
    monkeypatch.setenv("BACKLOG_SPACE", "space")
    monkeypatch.setenv("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("BOT_USER_ID", "123")
    # Provide API key via env to avoid secretsmanager dependency in test
    monkeypatch.setenv("BACKLOG_API_KEY", "x")

    fs3 = FakeS3()

    class BotoModule:
        def client(self, name: str):
            if name == "s3":
                return fs3
            if name == "bedrock-runtime":
                return FakeBedrock()
            raise ValueError(name)

    monkeypatch.setitem(idem.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(llm.__dict__, "boto3", BotoModule())

    # Replace BacklogClient with FakeBacklog inside handler
    monkeypatch.setitem(h.__dict__, "BacklogClient", FakeBacklog)

    body = {
        "comment": {
            "id": 999,
            "content": "@bot /summary\ncontext: https://example.com/x",
            "notifications": [{"user": {"id": 123}}],
        },
        "issue": {"issueKey": "PROJ-1", "id": 1},
    }
    event = {
        "headers": {"X-Webhook-Secret": "secret"},
        "body": json.dumps(body, ensure_ascii=False),
        "isBase64Encoded": False,
    }

    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == {"result": "ok"}
