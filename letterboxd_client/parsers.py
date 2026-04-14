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
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_BLOCK_RE = re.compile(
    r"<(?P<tag>article|div)[^>]+class=[\"'][^\"']*comment[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_BODY_RE = re.compile(
    r"<(?:div|p)[^>]+class=[\"'][^\"']*comment-body[^\"']*[\"'][^>]*>(.*?)</(?:div|p)>",
    re.IGNORECASE | re.DOTALL,
)


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._anchor: dict[str, Any] | None = None
        self.links: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attr_map = {key: value or "" for key, value in attrs}
            href = attr_map.get("href")
            if href:
                self._anchor = {"href": href, "text": "", "attrs": attr_map}

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            text = " ".join(self._anchor["text"].split())
            self.links.append({"href": self._anchor["href"], "text": text, "attrs": self._anchor["attrs"]})
            self._anchor = None


class _FormCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.inputs: dict[str, str] = {}
        self.forms: list[dict[str, Any]] = []
        self._current_form: dict[str, Any] | None = None
        self._textarea_name: str | None = None
        self._textarea_value: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._current_form = {
                "action": attr_map.get("action"),
                "attrs": attr_map,
                "inputs": {},
            }
            if self.action is None:
                self.action = attr_map.get("action")
                self.inputs = self._current_form["inputs"]
        elif tag == "input" and self._current_form is not None:
            name = attr_map.get("name")
            if name:
                input_type = attr_map.get("type", "").lower()
                if input_type in {"checkbox", "radio"} and "checked" not in attr_map:
                    return
                self._current_form["inputs"][name] = attr_map.get("value", "")
        elif tag == "textarea" and self._current_form is not None:
            self._textarea_name = attr_map.get("name")
            self._textarea_value = []
        elif tag == "button" and self._current_form is not None:
            name = attr_map.get("name")
            if name and name not in self._current_form["inputs"]:
                self._current_form["inputs"][name] = attr_map.get("value", "")

    def handle_data(self, data: str) -> None:
        if self._textarea_name is not None:
            self._textarea_value.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea" and self._current_form is not None and self._textarea_name:
            self._current_form["inputs"][self._textarea_name] = "".join(self._textarea_value).strip()
            self._textarea_name = None
            self._textarea_value = []
        elif tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


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


def extract_title(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if not match:
        return None
    return strip_html(unescape(match.group(1))).strip()


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


def extract_forms(html: str) -> list[dict[str, Any]]:
    parser = _FormCollector()
    parser.feed(html)
    return parser.forms


def strip_html(html: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", html)).split())


def trim_letterboxd_suffix(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.replace("• Letterboxd", "").replace("- Letterboxd", "").strip()
    if trimmed.endswith("’s profile"):
        trimmed = trimmed[: -len("’s profile")]
    return trimmed.strip()


def extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = _YEAR_RE.search(value)
    if not match:
        return None
    return int(match.group(0))


def collect_anchor_records(base_url: str, html: str) -> list[dict[str, Any]]:
    parser = _LinkCollector()
    parser.feed(html)
    records: list[dict[str, Any]] = []
    for record in parser.links:
        text = record["text"]
        attrs = record["attrs"]
        title = attrs.get("data-film-name") or attrs.get("title") or text
        href = urljoin(base_url, record["href"])
        records.append({"href": href, "text": text, "title": title, "attrs": attrs})
    return records


def collect_links(base_url: str, html: str) -> list[tuple[str, str]]:
    return [(record["href"], record["text"]) for record in collect_anchor_records(base_url, html) if record["text"]]


def guess_kind(url: str) -> str:
    path = urlparse(url).path
    if "/film/" in path:
        return "film"
    if "/log-entry/" in path or "/review/" in path:
        return "log"
    if "/list/" in path or path.rstrip("/").count("/") >= 2 and path.rstrip("/").endswith("list"):
        return "list"
    if "/story/" in path:
        return "story"
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
    for record in collect_anchor_records(base_url, html):
        url = record["href"]
        attrs = record["attrs"]
        kind = attrs.get("data-item-type", "").lower() or guess_kind(url)
        title = record["title"] or record["text"]
        if kind == "unknown" or url in seen or not title:
            continue
        seen.add(url)
        results.append(
            SearchResult(
                kind=kind,
                title=title,
                url=url,
                year=extract_year(attrs.get("data-film-release-year") or title),
                raw={"attrs": attrs, "text": record["text"]},
            )
        )
    return results


def parse_film(url: str, html: str, lid: str | None = None) -> Film:
    meta = extract_meta(html)
    json_ld = extract_json_ld(html)
    payload = next((item for item in json_ld if item.get("@type") == "Movie"), {})
    raw_title = payload.get("name") or trim_letterboxd_suffix(meta.get("og:title")) or trim_letterboxd_suffix(meta.get("twitter:title")) or trim_letterboxd_suffix(extract_title(html)) or "Unknown film"
    title = trim_letterboxd_suffix(raw_title) or "Unknown film"
    released = payload.get("datePublished") or title
    year = extract_year(released)
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
    display_name = trim_letterboxd_suffix(meta.get("og:title")) or trim_letterboxd_suffix(extract_title(html)) or username
    return Member(
        id=lid,
        username=username,
        url=url,
        display_name=display_name,
        bio=meta.get("description"),
        stats=extract_counts(html),
        raw={"meta": meta, "json_ld": extract_json_ld(html)},
    )


def parse_list(url: str, html: str, lid: str | None = None) -> ListResource:
    meta = extract_meta(html)
    title = trim_letterboxd_suffix(meta.get("og:title")) or trim_letterboxd_suffix(extract_title(html)) or "Untitled list"
    entries: list[ListEntry] = []
    seen: set[str] = set()
    for record in collect_anchor_records(url, html):
        link = record["href"]
        if guess_kind(link) != "film" or link in seen:
            continue
        seen.add(link)
        film_title = record["attrs"].get("data-film-name") or record["title"] or record["text"] or "Unknown film"
        entries.append(
            ListEntry(
                film=Film(id=None, title=film_title, url=link, year=extract_year(record["attrs"].get("data-film-release-year") or film_title)),
                rank=len(entries) + 1,
            )
        )
    return ListResource(
        id=lid,
        title=title,
        url=url,
        description=meta.get("description"),
        entries=entries,
        stats=extract_counts(html),
        raw={"meta": meta, "json_ld": extract_json_ld(html)},
    )


def parse_activity_page(url: str, html: str) -> Page[Activity]:
    actor = urlparse(url).path.strip("/").split("/", 1)[0] or None
    items = [
        Activity(kind=guess_kind(record["href"]), actor=actor, target=record["title"], url=record["href"], summary=record["text"] or record["title"], raw={"attrs": record["attrs"]})
        for record in collect_anchor_records(url, html)
        if guess_kind(record["href"]) in {"film", "list", "member", "log"}
    ]
    return Page(items=items, source_url=url)


def parse_comments(url: str, html: str) -> list[Comment]:
    comments: list[Comment] = []
    for match in _COMMENT_BLOCK_RE.finditer(html):
        block = match.group("body")
        body_match = _COMMENT_BODY_RE.search(block)
        body = strip_html(body_match.group(1) if body_match else block)
        author = None
        author_url = None
        for record in collect_anchor_records(url, block):
            if guess_kind(record["href"]) == "member":
                author = record["title"] or record["text"]
                author_url = record["href"]
                break
        if body:
            comments.append(Comment(id=None, author=author, body=body, url=author_url))
    if comments:
        return comments
    for record in collect_anchor_records(url, html):
        if not record["text"]:
            continue
        comments.append(Comment(id=None, author=None, body=record["text"], url=record["href"]))
    return comments


def parse_log_entry(url: str, html: str, lid: str | None = None) -> LogEntry:
    film = None
    for record in collect_anchor_records(url, html):
        link = record["href"]
        if guess_kind(link) == "film":
            film = Film(
                id=None,
                title=record["attrs"].get("data-film-name") or record["title"] or "Unknown film",
                url=link,
                year=extract_year(record["attrs"].get("data-film-release-year") or record["title"]),
            )
            break
    description = extract_meta(html).get("description")
    return LogEntry(
        id=lid,
        film=film,
        url=url,
        review=Review(text=description),
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
    feed_items = root.findall(".//item")
    if not feed_items:
        feed_items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "entry"]
    for item in feed_items:
        title = None
        link = None
        description = None
        for child in item:
            tag_name = child.tag.rsplit("}", 1)[-1]
            if tag_name == "title":
                title = "".join(child.itertext()).strip()
            elif tag_name == "link":
                link = child.attrib.get("href") or (child.text or "").strip()
            elif tag_name in {"description", "summary", "content"}:
                description = "".join(child.itertext()).strip()
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
