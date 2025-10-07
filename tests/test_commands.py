import pytest

from backlog_bot import commands


def test_is_bot_mentioned_true():
    comment = {
        "notifications": [
            {"user": {"id": 111}},
            {"user": {"id": 123}},
        ]
    }
    assert commands.is_bot_mentioned(comment, 123) is True


def test_is_bot_mentioned_false():
    assert commands.is_bot_mentioned({"notifications": []}, 1) is False


@pytest.mark.parametrize(
    "text,expect",
    [
        ("/ask これは?", {"cmd": "ask", "question": "これは?"}),
        ("/summary", {"cmd": "summary"}),
        ("/summary project style=narrative", {"cmd": "summary"}),
        ("/update", {"cmd": "update"}),
    ],
)
def test_parse_command(text, expect):
    assert commands.parse_command(text) == expect


def test_rule_based_summary():
    out = commands.rule_based_summary("タイトル", "説明がここにあります", ["最新コメント"])
    assert "要約" in out
    assert "タイトル" in out
