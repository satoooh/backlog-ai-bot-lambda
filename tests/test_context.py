from backlog_bot.context_fetch import (
    allowlisted,
    backlog_issue_to_text,
    backlog_wiki_to_text,
    extract_context_urls,
    is_http_url,
    parse_backlog_issue_url,
    parse_backlog_wiki_url,
)


def test_extract_context_urls():
    text = """Hello\ncontext: https://example.com/a https://x.invalid ftp://nope\n"""
    urls = extract_context_urls(text)
    assert urls == ["https://example.com/a", "https://x.invalid"]


def test_is_http_url():
    assert is_http_url("https://example.com")
    assert not is_http_url("mailto:x@y")


def test_allowlisted():
    assert allowlisted("https://docs.example.com/x", ["example.com"]) is True
    assert allowlisted("https://evil.com/x", ["example.com"]) is False


def test_parse_backlog_issue_url():
    base = "https://space.backlog.com"
    k, c = parse_backlog_issue_url("https://space.backlog.com/view/PROJ-12", base)
    assert (k, c) == ("PROJ-12", None)
    k, c = parse_backlog_issue_url("https://space.backlog.com/view/PROJ-12#comment-99", base)
    assert (k, c) == ("PROJ-12", 99)
    k, c = parse_backlog_issue_url("https://other/backlog/view/PROJ-12", base)
    assert (k, c) == (None, None)


def test_backlog_issue_to_text_truncates():
    issue = {"issueKey": "PROJ-1", "summary": "t", "description": "x" * 1000}
    text = backlog_issue_to_text(issue, [], max_chars=100)
    assert len(text) <= 100


def test_parse_backlog_wiki_url():
    base = "https://space.backlog.com"
    wid = parse_backlog_wiki_url("https://space.backlog.com/wiki/12345", base)
    assert wid == 12345
    wid = parse_backlog_wiki_url("https://space.backlog.com/wiki/PROJ/234", base)
    assert wid == 234
    assert parse_backlog_wiki_url("https://space.backlog.com/view/PROJ-1", base) is None


def test_backlog_wiki_to_text_truncates():
    wiki = {"name": "W", "content": "y" * 1000}
    text = backlog_wiki_to_text(wiki, [], max_chars=100)
    assert len(text) <= 100
