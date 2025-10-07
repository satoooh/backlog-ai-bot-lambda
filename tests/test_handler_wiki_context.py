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

    def get_wiki(self, wiki_id: int):
        return {"name": "W", "content": "wiki-body"}

    def list_wiki_attachments(self, wiki_id: int):
        return [{"name": "file.txt", "size": 10}]


def test_handler_uses_wiki_context(monkeypatch):
    import backlog_bot.idempotency as idem
    import backlog_bot.llm as llm

    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "secret")
    monkeypatch.setenv("IDEMPOTENCY_BUCKET", "b")
    monkeypatch.setenv("BACKLOG_SPACE", "space")
    monkeypatch.setenv("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("BOT_USER_ID", "123")
    monkeypatch.setenv("BACKLOG_API_KEY", "x")

    fs3 = FakeS3()
    fb = FakeBacklog()

    class BotoModule:
        def client(self, name: str):
            if name == "s3":
                return fs3
            if name == "bedrock-runtime":
                # Return minimal OK for LLM
                class R:
                    @staticmethod
                    def read():
                        return json.dumps({"content": [{"text": "OK"}]}).encode("utf-8")

                class BR:
                    def invoke_model(self, **_kw):
                        return {"body": R()}

                return BR()
            raise ValueError(name)

    monkeypatch.setitem(idem.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(llm.__dict__, "boto3", BotoModule())
    monkeypatch.setitem(h.__dict__, "BacklogClient", lambda *_a, **_k: fb)

    body = {
        "type": 3,
        "content": {
            "comment": {
                "id": 2000,
                "content": "@bot /summary\ncontext: https://space.backlog.com/wiki/12345",
                "notifications": [{"user": {"id": 123}}],
                "createdUser": {"id": 123},
            },
            "key_id": "PROJ-3",
        },
    }
    event = {
        "headers": {"X-Webhook-Secret": "secret"},
        "body": json.dumps(body, ensure_ascii=False),
        "isBase64Encoded": False,
    }

    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # summary replies include **参照コンテキスト** section when used
    assert any("参照コンテキスト" in c for c in fb.posted)
