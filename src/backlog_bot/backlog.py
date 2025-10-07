"""
Minimal Backlog API client (v2) using stdlib urllib.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class BacklogClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_api = base_url.rstrip("/") + "/api/v2"
        self.api_key = api_key

    # ----- Helpers -----
    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        p = {"apiKey": self.api_key}
        if params:
            p.update(params)
        return self.base_api + path + "?" + urllib.parse.urlencode(p)

    def _get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "BacklogBot/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310
            data = resp.read()
        return json.loads(data.decode("utf-8"))

    def _post_json(self, url: str, form: dict[str, Any]) -> Any:
        body = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "BacklogBot/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310
            data = resp.read()
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    # ----- Public APIs -----
    def get_issue(self, issue_id_or_key: str) -> dict[str, Any]:
        url = self._url(f"/issues/{urllib.parse.quote(issue_id_or_key)}")
        return self._get_json(url)

    def list_comments(
        self, issue_id_or_key: str, count: int = 30, order: str = "desc"
    ) -> list[dict[str, Any]]:
        url = self._url(
            f"/issues/{urllib.parse.quote(issue_id_or_key)}/comments",
            {"count": count, "order": order},
        )
        data = self._get_json(url)
        return list(data) if isinstance(data, list) else []

    def post_comment(self, issue_id_or_key: str, content: str) -> dict[str, Any]:
        url = self._url(f"/issues/{urllib.parse.quote(issue_id_or_key)}/comments")
        return self._post_json(url, {"content": content})

    # ----- Wiki APIs -----
    def get_wiki(self, wiki_id: int) -> dict[str, Any]:
        url = self._url(f"/wikis/{int(wiki_id)}")
        return self._get_json(url)

    def list_wiki_attachments(self, wiki_id: int) -> list[dict[str, Any]]:
        url = self._url(f"/wikis/{int(wiki_id)}/attachments")
        data = self._get_json(url)
        return list(data) if isinstance(data, list) else []
