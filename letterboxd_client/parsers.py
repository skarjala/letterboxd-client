"""HTML and feed parsing helpers."""

from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from .errors import MarkupChanged
from .models import Activity, Comment, Film, ListEntry, ListResource, LogEntry, Member, Page, Review, SearchResult

_SCRIPT_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_META_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']([^\"']+)[\"'][^>]+content=[\"']([^\"']*)[\"'][^>]*>",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"([A-Za-z][A-Za-z ]+?)\s*([0-9][0-9,]*)")


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._anchor: dict[str, str] | None = None
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attr_map = {key: value or "" for key, value in attrs}
            href = attr_map.get("href")
            if href:
                self._anchor = {"href": href, "text": ""}

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            text = " ".join(self._anchor["text"].split())
            self.links.append((self._anchor["href"], text))
            self._anchor = None


class _FormCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.inputs: dict[str, str] = {}
        self._seen_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form" and not self._seen_form:
            self._seen_form = True
            self.action = attr_map.get("action")
        elif tag == "input" and self._seen_form:
            name = attr_map.get("name")
            if name:
                self.inputs[name] = attr_map.get("value", "")


def extract_json_ld(html: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for match in _SCRIPT_RE.findall(html):
        try:
            decoded = json.loads(unescape(match))
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            payloads.append(decoded)
        elif isinstance(decoded, list):
            payloads.extend(item for item in decoded if isinstance(item, dict))
    return payloads


def extract_meta(html: str) -> dict[str, str]:
    return {key: unescape(value) for key, value in _META_RE.findall(html)}


def extract_counts(html: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, number in _COUNT_RE.findall(html):
        normalised = label.strip().lower().replace(" ", "_")
        counts.setdefault(normalised, int(number.replace(",", "")))
    return counts


def extract_form(html: str) -> tuple[str | None, dict[str, str]]:
    parser = _FormCollector()
    parser.feed(html)
    return parser.action, parser.inputs


def collect_links(base_url: str, html: str) -> list[tuple[str, str]]:
    parser = _LinkCollector()
    parser.feed(html)
    return [(urljoin(base_url, href), text) for href, text in parser.links if text]


def guess_kind(url: str) -> str:
    path = urlparse(url).path
    if "/film/" in path:
        return "film"
    if "/list/" in path or path.rstrip("/").count("/") >= 2 and path.rstrip("/").endswith("list"):
        return "list"
    if path.endswith("/watchlist/"):
        return "watchlist"
    if path.endswith("/activity/"):
        return "activity"
    if path.count("/") <= 2 and path.strip("/"):
        return "member"
    return "unknown"


def parse_search_results(base_url: str, html: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for url, text in collect_links(base_url, html):
        kind = guess_kind(url)
        if kind == "unknown" or url in seen:
            continue
        seen.add(url)
        results.append(SearchResult(kind=kind, title=text, url=url))
    return results


def parse_film(url: str, html: str, lid: str | None = None) -> Film:
    meta = extract_meta(html)
    json_ld = extract_json_ld(html)
    payload = next((item for item in json_ld if item.get("@type") == "Movie"), {})
    title = payload.get("name") or meta.get("og:title") or meta.get("twitter:title") or "Unknown film"
    year = None
    released = payload.get("datePublished")
    if isinstance(released, str) and len(released) >= 4 and released[:4].isdigit():
        year = int(released[:4])
    return Film(
        id=lid,
        title=title,
        url=url,
        year=year,
        summary=payload.get("description") or meta.get("description"),
        stats=extract_counts(html),
        raw={"meta": meta, "json_ld": payload},
    )


def parse_member(url: str, html: str, lid: str | None = None) -> Member:
    meta = extract_meta(html)
    username = urlparse(url).path.strip("/").split("/", 1)[0] or "unknown"
    return Member(
        id=lid,
        username=username,
        url=url,
        display_name=meta.get("og:title") or username,
        bio=meta.get("description"),
        stats=extract_counts(html),
        raw={"meta": meta, "json_ld": extract_json_ld(html)},
    )


def parse_list(url: str, html: str, lid: str | None = None) -> ListResource:
    meta = extract_meta(html)
    entries = [ListEntry(film=parse_film(link, "", None)) for link, _ in collect_links(url, html) if guess_kind(link) == "film"]
    return ListResource(
        id=lid,
        title=meta.get("og:title") or "Untitled list",
        url=url,
        description=meta.get("description"),
        entries=entries,
        stats=extract_counts(html),
        raw={"meta": meta, "json_ld": extract_json_ld(html)},
    )


def parse_activity_page(url: str, html: str) -> Page[Activity]:
    items = [
        Activity(kind=guess_kind(link), actor=None, target=text, url=link, summary=text, raw={})
        for link, text in collect_links(url, html)
        if guess_kind(link) in {"film", "list", "member"}
    ]
    return Page(items=items, source_url=url)


def parse_comments(url: str, html: str) -> list[Comment]:
    comments: list[Comment] = []
    for link, text in collect_links(url, html):
        if not text:
            continue
        comments.append(Comment(id=None, author=None, body=text, url=link))
    return comments


def parse_log_entry(url: str, html: str, lid: str | None = None) -> LogEntry:
    film = None
    for link, _ in collect_links(url, html):
        if guess_kind(link) == "film":
            film = parse_film(link, "", None)
            break
    return LogEntry(
        id=lid,
        film=film,
        url=url,
        review=Review(text=extract_meta(html).get("description")),
        stats=extract_counts(html),
        comments=parse_comments(url, html),
        raw={"meta": extract_meta(html), "json_ld": extract_json_ld(html)},
    )


def parse_feed(xml_text: str) -> Page[Activity]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise MarkupChanged("RSS feed parsing failed") from exc

    items: list[Activity] = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        description = item.findtext("description")
        if not title:
            continue
        items.append(
            Activity(
                kind=guess_kind(link or ""),
                actor=None,
                target=title,
                url=link,
                summary=description,
                raw={},
            )
        )
    return Page(items=items)

