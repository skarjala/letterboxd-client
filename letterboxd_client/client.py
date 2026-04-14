"""High-level client and namespace implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from . import bulk as bulk_mod
from . import exports as exports_mod
from .errors import UnsupportedFlow
from .models import (
    Activity,
    Film,
    FilmRelationship,
    ListResource,
    LogEntry,
    Member,
    MemberRelationship,
    Page,
    SearchResult,
)
from .parsers import (
    collect_links,
    guess_kind,
    parse_activity_page,
    parse_comments,
    parse_feed,
    parse_film,
    parse_list,
    parse_log_entry,
    parse_member,
    parse_search_results,
)
from .transport import LetterboxdTransport


def _ensure_page_url(path_or_url: str, base_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if path_or_url.startswith("/"):
        return base_url.rstrip("/") + path_or_url
    return base_url.rstrip("/") + "/" + path_or_url.lstrip("/")


class _BaseNamespace:
    def __init__(self, client: "LetterboxdClient") -> None:
        self._client = client

    @property
    def transport(self) -> LetterboxdTransport:
        return self._client.transport

    def _require_api(self) -> None:
        if "Authorization" not in self.transport.client.headers:
            raise UnsupportedFlow(
                "This mutation currently requires an API bearer token configured on the client."
            )

    def _resolve_reference(self, value: str, *, default_prefix: str = "") -> tuple[str, str | None]:
        if default_prefix and not value.startswith("http") and not value.startswith("/"):
            value = f"{default_prefix.rstrip('/')}/{value.strip('/')}/"
        return self.transport.resolve_url(value)


class AuthNamespace(_BaseNamespace):
    def login(self, username: str, password: str) -> "LetterboxdClient":
        self.transport.login(username, password)
        return self._client

    def logout(self) -> None:
        self.transport.client.cookies.clear()
        self.transport.client.headers.pop("Authorization", None)

    def from_cookies(self, cookies: dict[str, str]) -> "LetterboxdClient":
        self.transport.set_cookies(cookies)
        return self._client

    def refresh_session(self) -> None:
        self.transport.get_html("/settings/")

    def check_username(self, username: str) -> dict[str, Any]:
        self._require_api()
        return self.transport.get_json("/auth/username-check", api=True, params={"username": username})

    def get_login_token(self) -> dict[str, Any]:
        self._require_api()
        return self.transport.get_json("/auth/get-login-token", api=True)


class SearchNamespace(_BaseNamespace):
    def search(self, query: str, kind: str | None = None) -> list[SearchResult]:
        html = self.transport.get_html(f"/search/{quote(query)}/")
        results = parse_search_results(self._client.base_url, html)
        if kind is None:
            return results
        return [item for item in results if item.kind == kind]

    def autocomplete(self, query: str) -> list[SearchResult]:
        return self.search(query)[:10]

    def resolve(self, url_or_boxd_it: str) -> SearchResult:
        resolved_url, lid = self.transport.resolve_url(url_or_boxd_it)
        return SearchResult(kind=guess_kind(resolved_url), title=resolved_url.rstrip("/").split("/")[-1], url=resolved_url, id=lid)


class FilmsNamespace(_BaseNamespace):
    def _film_url(self, film: str) -> tuple[str, str | None]:
        return self._resolve_reference(film, default_prefix="/film")

    def get(self, film: str) -> Film:
        resolved_url, lid = self._film_url(film)
        html = self.transport.get_html(resolved_url)
        return parse_film(resolved_url, html, lid=lid)

    def list(self, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[Film]:
        params = dict(filters or {})
        if cursor:
            params["cursor"] = cursor
        html = self.transport.get_html("/films/", params=params or None)
        items = [
            Film(id=result.id, title=result.title, url=result.url, raw=result.raw)
            for result in parse_search_results(self._client.base_url, html)
            if result.kind == "film"
        ]
        return Page(items=items, source_url=_ensure_page_url("/films/", self._client.base_url))

    def stats(self, film: str) -> dict[str, Any]:
        return self.get(film).stats

    def availability(self, film: str) -> list[str]:
        resolved_url, _ = self._film_url(film)
        html = self.transport.get_html(resolved_url)
        services: list[str] = []
        for link, text in collect_links(resolved_url, html):
            if "/on/" in link or "/service/" in link:
                services.append(text)
        return list(dict.fromkeys(service for service in services if service))

    def relationship(self, film: str) -> FilmRelationship:
        if "Authorization" in self.transport.client.headers:
            _, lid = self._film_url(film)
            if lid:
                payload = self.transport.get_json(f"/film/{lid}/me", api=True)
                return FilmRelationship(raw=payload)
        scraped = self.get(film)
        return scraped.relationship or FilmRelationship(raw=scraped.raw)

    def watchlist(self, film: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._film_url(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"inWatchlist": enabled},
            expected_status=(200,),
        ).json()

    def rate(self, film: str, rating: float) -> dict[str, Any]:
        self._require_api()
        _, lid = self._film_url(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"rating": rating},
            expected_status=(200,),
        ).json()

    def like(self, film: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._film_url(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"liked": enabled},
            expected_status=(200,),
        ).json()

    def mark_watched(self, film: str, watched: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._film_url(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"watched": watched},
            expected_status=(200,),
        ).json()


class MembersNamespace(_BaseNamespace):
    def _member_url(self, member: str) -> tuple[str, str | None]:
        if member.startswith("http"):
            return self.transport.resolve_url(member)
        cleaned = member.strip("/")
        return self.transport.resolve_url(f"/{cleaned}/")

    def get(self, member: str) -> Member:
        resolved_url, lid = self._member_url(member)
        html = self.transport.get_html(resolved_url)
        return parse_member(resolved_url, html, lid=lid)

    def me(self) -> Member:
        self._require_api()
        payload = self.transport.get_json("/me", api=True)
        data = payload.get("data", payload)
        return Member(
            id=data.get("id"),
            username=data.get("username", "me"),
            url=data.get("links", {}).get("self", self._client.base_url),
            display_name=data.get("displayName"),
            bio=data.get("bio"),
            stats=data,
            raw=data,
        )

    def activity(self, member: str, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[Activity]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/activity/"
        html = self.transport.get_html(path, params=(filters or None))
        return parse_activity_page(_ensure_page_url(path, self._client.base_url), html)

    def stats(self, member: str) -> dict[str, Any]:
        return self.get(member).stats

    def watchlist(self, member: str, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[Film]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/watchlist/"
        html = self.transport.get_html(path, params=(filters or None))
        items = [
            Film(id=result.id, title=result.title, url=result.url, raw=result.raw)
            for result in parse_search_results(self._client.base_url, html)
            if result.kind == "film"
        ]
        return Page(items=items, source_url=_ensure_page_url(path, self._client.base_url))

    def followers(self, member: str) -> Page[Member]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/followers/"
        html = self.transport.get_html(path)
        items = [
            Member(id=result.id, username=urlparse(result.url).path.strip("/"), url=result.url, display_name=result.title, raw=result.raw)
            for result in parse_search_results(self._client.base_url, html)
            if result.kind == "member"
        ]
        return Page(items=items, source_url=_ensure_page_url(path, self._client.base_url))

    def following(self, member: str) -> Page[Member]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/following/"
        html = self.transport.get_html(path)
        items = [
            Member(id=result.id, username=urlparse(result.url).path.strip("/"), url=result.url, display_name=result.title, raw=result.raw)
            for result in parse_search_results(self._client.base_url, html)
            if result.kind == "member"
        ]
        return Page(items=items, source_url=_ensure_page_url(path, self._client.base_url))

    def follow(self, member: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._member_url(member)
        return self.transport.request(
            "PATCH",
            f"/member/{lid}/me",
            api=True,
            json={"following": enabled},
            expected_status=(200,),
        ).json()

    def block(self, member: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._member_url(member)
        return self.transport.request(
            "PATCH",
            f"/member/{lid}/me",
            api=True,
            json={"blocked": enabled},
            expected_status=(200,),
        ).json()


class LogsNamespace(_BaseNamespace):
    def _log_url(self, log_entry: str) -> tuple[str, str | None]:
        return self._resolve_reference(log_entry, default_prefix="/log-entry")

    def list(
        self,
        member: str | None = None,
        film: str | None = None,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
    ) -> Page[LogEntry]:
        if "Authorization" in self.transport.client.headers and not member and not film:
            payload = self.transport.get_json("/log-entries", api=True, params={**(filters or {}), **({"cursor": cursor} if cursor else {})})
            items = [LogEntry(id=item.get("id"), film=None, url=item.get("links", {}).get("self", ""), raw=item) for item in payload.get("items", [])]
            return Page(items=items, next_cursor=payload.get("next"))
        if member:
            base_url, _ = self._client.members._member_url(member)
            path = urlparse(base_url).path.rstrip("/") + "/films/diary/"
        elif film:
            base_url, _ = self._client.films._film_url(film)
            path = urlparse(base_url).path
        else:
            path = "/films/diary/"
        html = self.transport.get_html(path, params=(filters or None))
        items: list[LogEntry] = []
        for result in parse_search_results(self._client.base_url, html):
            if result.kind == "film":
                film_obj = Film(id=result.id, title=result.title, url=result.url, raw=result.raw)
                items.append(LogEntry(id=None, film=film_obj, url=result.url, raw={"source": path}))
        return Page(items=items, source_url=_ensure_page_url(path, self._client.base_url))

    def get(self, log_entry: str) -> LogEntry:
        resolved_url, lid = self._log_url(log_entry)
        html = self.transport.get_html(resolved_url)
        return parse_log_entry(resolved_url, html, lid=lid)

    def comments(self, log_entry: str) -> list[Any]:
        return self.get(log_entry).comments

    def stats(self, log_entry: str) -> dict[str, Any]:
        return self.get(log_entry).stats

    def create(self, **payload: Any) -> dict[str, Any]:
        self._require_api()
        return self.transport.request("POST", "/log-entries", api=True, json=payload, expected_status=(200, 201)).json()

    def update(self, log_entry: str, **payload: Any) -> dict[str, Any]:
        self._require_api()
        _, lid = self._log_url(log_entry)
        return self.transport.request("PATCH", f"/log-entry/{lid}", api=True, json=payload, expected_status=(200,)).json()

    def delete(self, log_entry: str) -> None:
        self._require_api()
        _, lid = self._log_url(log_entry)
        self.transport.request("DELETE", f"/log-entry/{lid}", api=True, expected_status=(204,))

    def comment(self, log_entry: str, text: str) -> dict[str, Any]:
        self._require_api()
        _, lid = self._log_url(log_entry)
        return self.transport.request(
            "POST",
            f"/log-entry/{lid}/comments",
            api=True,
            json={"message": text},
            expected_status=(200, 201),
        ).json()

    def like(self, log_entry: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._log_url(log_entry)
        return self.transport.request(
            "PATCH",
            f"/log-entry/{lid}/me",
            api=True,
            json={"liked": enabled},
            expected_status=(200,),
        ).json()


class ListsNamespace(_BaseNamespace):
    def _list_url(self, list_id: str) -> tuple[str, str | None]:
        if list_id.startswith("http"):
            return self.transport.resolve_url(list_id)
        if list_id.startswith("/"):
            return self.transport.resolve_url(list_id)
        return self.transport.resolve_url(f"/{list_id.strip('/')}/")

    def list(self, member: str | None = None, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[ListResource]:
        if member:
            member_url, _ = self._client.members._member_url(member)
            path = urlparse(member_url).path.rstrip("/") + "/lists/"
        else:
            path = "/lists/"
        html = self.transport.get_html(path, params={**(filters or {}), **({"cursor": cursor} if cursor else {})})
        items = [
            ListResource(id=result.id, title=result.title, url=result.url, raw=result.raw)
            for result in parse_search_results(self._client.base_url, html)
            if result.kind == "list"
        ]
        return Page(items=items, source_url=_ensure_page_url(path, self._client.base_url))

    def get(self, list_id: str) -> ListResource:
        resolved_url, lid = self._list_url(list_id)
        html = self.transport.get_html(resolved_url)
        return parse_list(resolved_url, html, lid=lid)

    def entries(self, list_id: str) -> list[Any]:
        return self.get(list_id).entries

    def comments(self, list_id: str) -> list[Any]:
        resolved_url, _ = self._list_url(list_id)
        html = self.transport.get_html(resolved_url)
        return parse_comments(resolved_url, html)

    def stats(self, list_id: str) -> dict[str, Any]:
        return self.get(list_id).stats

    def create(self, **payload: Any) -> dict[str, Any]:
        self._require_api()
        return self.transport.request("POST", "/lists", api=True, json=payload, expected_status=(200, 201)).json()

    def update(self, list_id: str, **payload: Any) -> dict[str, Any]:
        self._require_api()
        _, lid = self._list_url(list_id)
        return self.transport.request("PATCH", f"/list/{lid}", api=True, json=payload, expected_status=(200,)).json()

    def delete(self, list_id: str) -> None:
        self._require_api()
        _, lid = self._list_url(list_id)
        self.transport.request("DELETE", f"/list/{lid}", api=True, expected_status=(204,))

    def upsert_entries(self, list_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_api()
        _, lid = self._list_url(list_id)
        return self.transport.request(
            "PATCH",
            "/lists",
            api=True,
            json={"target": lid, "entries": entries},
            expected_status=(200,),
        ).json()

    def comment(self, list_id: str, text: str) -> dict[str, Any]:
        self._require_api()
        _, lid = self._list_url(list_id)
        return self.transport.request(
            "POST",
            f"/list/{lid}/comments",
            api=True,
            json={"message": text},
            expected_status=(200, 201),
        ).json()

    def like(self, list_id: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        _, lid = self._list_url(list_id)
        return self.transport.request(
            "PATCH",
            f"/list/{lid}/me",
            api=True,
            json={"liked": enabled},
            expected_status=(200,),
        ).json()


class FeedsNamespace(_BaseNamespace):
    def member_rss(self, member: str, kind: str = "activity") -> Page[Activity]:
        base_url, _ = self._client.members._member_url(member)
        base_path = urlparse(base_url).path.rstrip("/")
        kind_map = {
            "activity": f"{base_path}/rss/",
            "reviews": f"{base_path}/reviews/rss/",
            "lists": f"{base_path}/lists/rss/",
            "watchlist": f"{base_path}/watchlist/rss/",
        }
        xml_text = self.transport.get_html(kind_map.get(kind, kind_map["activity"]))
        return parse_feed(xml_text)

    def news(self) -> Page[Activity]:
        html = self.transport.get_html("/news/")
        return parse_activity_page(_ensure_page_url("/news/", self._client.base_url), html)

    def stories(self) -> Page[Activity]:
        html = self.transport.get_html("/stories/")
        return parse_activity_page(_ensure_page_url("/stories/", self._client.base_url), html)


class ExportsNamespace(_BaseNamespace):
    def load_account_export_zip(self, path: str | Path) -> dict[str, list[dict[str, Any]]]:
        return exports_mod.load_account_export_zip(path)

    def parse_letterboxd_csv(self, path: str | Path) -> list[dict[str, Any]]:
        return exports_mod.parse_letterboxd_csv(path)

    def parse_imdb_export(self, path: str | Path) -> list[dict[str, Any]]:
        return exports_mod.parse_imdb_export(path)

    def normalize(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return exports_mod.normalize(data)

    def to_jsonl(self, data: list[Any], path: str | Path | None = None) -> str:
        return exports_mod.to_jsonl(data, path=path)


class BulkNamespace(_BaseNamespace):
    def iterate_all(self, call: Any, *args: Any, **kwargs: Any) -> Any:
        return bulk_mod.iterate_all(call, *args, **kwargs)

    def hydrate_many(self, ids: list[str], resource: str) -> list[Any]:
        mapping = {
            "film": self._client.films.get,
            "member": self._client.members.get,
            "list": self._client.lists.get,
            "log": self._client.logs.get,
        }
        getter = mapping[resource]
        return bulk_mod.hydrate_many(ids, getter)

    def to_pandas(self, data: list[Any]) -> Any:
        return bulk_mod.to_pandas(data)

    def to_polars(self, data: list[Any]) -> Any:
        return bulk_mod.to_polars(data)

    def to_arrow(self, data: list[Any]) -> Any:
        return bulk_mod.to_arrow(data)


class TaxonomyNamespace(_BaseNamespace):
    def _collect_taxonomy(self, path: str) -> list[str]:
        html = self.transport.get_html(path)
        labels = [text for link, text in collect_links(_ensure_page_url(path, self._client.base_url), html) if link != _ensure_page_url(path, self._client.base_url)]
        return list(dict.fromkeys(label for label in labels if label))

    def genres(self) -> list[str]:
        return self._collect_taxonomy("/films/genre/")

    def languages(self) -> list[str]:
        return self._collect_taxonomy("/films/language/")

    def countries(self) -> list[str]:
        return self._collect_taxonomy("/films/country/")

    def services(self) -> list[str]:
        return self._collect_taxonomy("/films/on/")

    def availability_types(self) -> list[str]:
        return ["subscription", "rent", "buy", "cinema", "physical"]


class LetterboxdClient:
    """High-level client facade."""

    def __init__(
        self,
        *,
        base_url: str = "https://letterboxd.com",
        api_base: str = "https://api.letterboxd.com/api/v0",
        api_bearer_token: str | None = None,
        timeout: float = 20.0,
        user_agent: str = "letterboxd-client/0.1.0",
        transport: LetterboxdTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport or LetterboxdTransport(
            base_url=base_url,
            api_base=api_base,
            api_bearer_token=api_bearer_token,
            timeout=timeout,
            user_agent=user_agent,
        )

        self.auth = AuthNamespace(self)
        self.search = SearchNamespace(self)
        self.films = FilmsNamespace(self)
        self.members = MembersNamespace(self)
        self.logs = LogsNamespace(self)
        self.lists = ListsNamespace(self)
        self.feeds = FeedsNamespace(self)
        self.exports = ExportsNamespace(self)
        self.bulk = BulkNamespace(self)
        self.taxonomy = TaxonomyNamespace(self)

    def close(self) -> None:
        self.transport.close()

    def login(self, username: str, password: str) -> "LetterboxdClient":
        return self.auth.login(username, password)

    @classmethod
    def from_cookies(cls, cookies: dict[str, str], **kwargs: Any) -> "LetterboxdClient":
        client = cls(**kwargs)
        client.auth.from_cookies(cookies)
        return client

    def __enter__(self) -> "LetterboxdClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
