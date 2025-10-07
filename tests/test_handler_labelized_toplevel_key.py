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
        return {"summary": "S", "description": "D"}

    def list_comments(self, issue_id_or_key: str, count: int = 30):
        return [{"content": "c1"}]

    def post_comment(self, issue_id_or_key: str, content: str):
        self.posted.append(content)
        return {"ok": True}


def test_labelized_top_level_key_triggers(monkeypatch):
    import backlog_bot.idempotency as idem
    import backlog_bot.llm as llm

    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "secret")
    monkeypatch.setenv("IDEMPOTENCY_BUCKET", "b")
    monkeypatch.setenv("BACKLOG_SPACE", "space")
    monkeypatch.setenv("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("BOT_USER_ID", "123")
    monkeypatch.setenv("BACKLOG_API_KEY", "x")

    fs3 = FakeS3()

    class BR:
        def invoke_model(self, **_kw):
            body = json.dumps({"content": [{"text": "OK"}]})
            return {"body": type("R", (), {"read": lambda self=None: body.encode("utf-8")})()}

    class BotoModule:
        def client(self, name: str):
            if name == "s3":
                return fs3
            if name == "bedrock-runtime":
                return BR()
            raise ValueError(name)

    monkeypatch.setitem(idem.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(llm.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(h.__dict__, "BacklogClient", lambda *_a, **_k: FakeBacklog())

    # top-level Key ID, content has only comment/changes/diff
    payload = {
        "type": 3,
        "ID": 1001,
        "Key ID": "PROJ-1001",
        "content": {
            "comment": "@bot /summary",
            "changes": [],
            "diff": "",
        },
    }
    event = {
        "headers": {"X-Webhook-Secret": "secret"},
        "body": json.dumps(payload, ensure_ascii=False),
        "isBase64Encoded": False,
    }
    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
