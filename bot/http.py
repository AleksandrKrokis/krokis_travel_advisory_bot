"""HTTP helpers."""

import html
import re
import time
import xml.etree.ElementTree as ET

import httpx

from .config import USER_AGENT

_client = httpx.Client(
    headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
    timeout=30.0,
    follow_redirects=True,
)


def get(url: str, params: dict | None = None, retries: int = 2, **kw) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = _client.get(url, params=params, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            last = e
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last  # type: ignore[misc]


def post(url: str, **kw) -> httpx.Response:
    return _client.post(url, **kw)


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_rss(text: str) -> list[dict]:
    """Minimal RSS 2.0 parser: [{guid, title, link, description, categories}]"""
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    items = []
    for it in root.iter("item"):
        def t(tag):
            el = it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        link = t("link")
        items.append({
            "guid": t("guid") or link or t("title"),
            "title": strip_html(t("title")),
            "link": link,
            "description": strip_html(t("description")),
            "categories": [c.text or "" for c in it.findall("category")],
        })
    return items
