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
    extract_next_cursor_from_html,
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

_UNSET = object()


def _ensure_page_url(path_or_url: str, base_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if path_or_url.startswith("/"):
        return base_url.rstrip("/") + path_or_url
    return base_url.rstrip("/") + "/" + path_or_url.lstrip("/")


def _drop_unset(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not _UNSET}


def _film_from_result(result: SearchResult) -> Film:
    return Film(
        id=result.id,
        title=result.title,
        url=result.url,
        year=result.year,
        summary=result.summary,
        raw=result.raw,
    )


def _member_from_result(result: SearchResult) -> Member:
    username = result.id or urlparse(result.url).path.strip("/").split("/", 1)[0]
    return Member(
        id=result.id or username,
        username=username,
        url=result.url,
        display_name=result.title,
        raw=result.raw,
    )


def _list_from_result(result: SearchResult) -> ListResource:
    return ListResource(
        id=result.id,
        title=result.title,
        url=result.url,
        raw=result.raw,
    )


def _log_from_result(result: SearchResult) -> LogEntry:
    attrs = result.raw.get("attrs", {})
    film_name = attrs.get("data-film-name")
    film_year = None
    if attrs.get("data-film-release-year"):
        try:
            film_year = int(attrs["data-film-release-year"])
        except ValueError:
            film_year = None
    film = None
    if film_name or result.kind == "film":
        film = Film(
            id=attrs.get("data-film-id") or (result.id if result.kind == "film" else None),
            title=film_name or result.title,
            url=attrs.get("data-film-link") or result.url,
            year=film_year or result.year,
            raw=result.raw,
        )
    return LogEntry(id=result.id, film=film, url=result.url, raw=result.raw)


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

    def _require_lid(self, value: str, *, default_prefix: str = "") -> str:
        _, lid = self._resolve_reference(value, default_prefix=default_prefix)
        if not lid:
            raise UnsupportedFlow(f"Could not resolve a Letterboxd ID for {value!r}")
        return lid


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
        kind = guess_kind(resolved_url)
        title = resolved_url.rstrip("/").split("/")[-1]
        year = None
        summary = None
        if kind == "film":
            film = self._client.films.get(resolved_url)
            title = film.title
            year = film.year
            summary = film.summary
        elif kind == "member":
            member = self._client.members.get(resolved_url)
            title = member.display_name or member.username
            summary = member.bio
        elif kind == "list":
            list_resource = self._client.lists.get(resolved_url)
            title = list_resource.title
            summary = list_resource.description
        elif kind == "log":
            log_entry = self._client.logs.get(resolved_url)
            if log_entry.film is not None:
                title = log_entry.film.title
            if log_entry.review is not None:
                summary = log_entry.review.text
        return SearchResult(kind=kind, title=title, url=resolved_url, id=lid, year=year, summary=summary)


class FilmsNamespace(_BaseNamespace):
    def _film_url(self, film: str) -> tuple[str, str | None]:
        return self._resolve_reference(film, default_prefix="/film")

    def _film_lid(self, film: str) -> str:
        return self._require_lid(film, default_prefix="/film")

    def get(self, film: str) -> Film:
        resolved_url, lid = self._film_url(film)
        html = self.transport.get_html(resolved_url)
        return parse_film(resolved_url, html, lid=lid)

    def list(self, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[Film]:
        params = dict(filters or {})
        if cursor:
            params["cursor"] = cursor
        html = self.transport.get_html("/films/", params=params or None)
        items = [_film_from_result(result) for result in parse_search_results(self._client.base_url, html) if result.kind == "film"]
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url("/films/", self._client.base_url),
        )

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
        lid = self._film_lid(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"inWatchlist": enabled},
            expected_status=(200,),
        ).json()

    def rate(self, film: str, rating: float) -> dict[str, Any]:
        self._require_api()
        lid = self._film_lid(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"rating": rating},
            expected_status=(200,),
        ).json()

    def like(self, film: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._film_lid(film)
        return self.transport.request(
            "PATCH",
            f"/film/{lid}/me",
            api=True,
            json={"liked": enabled},
            expected_status=(200,),
        ).json()

    def mark_watched(self, film: str, watched: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._film_lid(film)
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

    def _member_lid(self, member: str) -> str:
        if member.startswith("http"):
            return self._require_lid(member)
        cleaned = member.strip("/")
        return self._require_lid(f"/{cleaned}/")

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
        items = [_film_from_result(result) for result in parse_search_results(self._client.base_url, html) if result.kind == "film"]
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url(path, self._client.base_url),
        )

    def followers(self, member: str) -> Page[Member]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/followers/"
        html = self.transport.get_html(path)
        items = [_member_from_result(result) for result in parse_search_results(self._client.base_url, html) if result.kind == "member"]
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url(path, self._client.base_url),
        )

    def following(self, member: str) -> Page[Member]:
        resolved_url, _ = self._member_url(member)
        path = urlparse(resolved_url).path.rstrip("/") + "/following/"
        html = self.transport.get_html(path)
        items = [_member_from_result(result) for result in parse_search_results(self._client.base_url, html) if result.kind == "member"]
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url(path, self._client.base_url),
        )

    def follow(self, member: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._member_lid(member)
        return self.transport.request(
            "PATCH",
            f"/member/{lid}/me",
            api=True,
            json={"following": enabled},
            expected_status=(200,),
        ).json()

    def block(self, member: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._member_lid(member)
        return self.transport.request(
            "PATCH",
            f"/member/{lid}/me",
            api=True,
            json={"blocking": enabled},
            expected_status=(200,),
        ).json()


class LogsNamespace(_BaseNamespace):
    def _log_url(self, log_entry: str) -> tuple[str, str | None]:
        return self._resolve_reference(log_entry, default_prefix="/log-entry")

    def _log_lid(self, log_entry: str) -> str:
        return self._require_lid(log_entry, default_prefix="/log-entry")

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
            if result.kind == "log":
                items.append(_log_from_result(result))
            elif result.kind == "film":
                items.append(_log_from_result(result))
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url(path, self._client.base_url),
        )

    def get(self, log_entry: str) -> LogEntry:
        resolved_url, lid = self._log_url(log_entry)
        html = self.transport.get_html(resolved_url)
        return parse_log_entry(resolved_url, html, lid=lid)

    def comments(self, log_entry: str) -> list[Any]:
        return self.get(log_entry).comments

    def stats(self, log_entry: str) -> dict[str, Any]:
        return self.get(log_entry).stats

    def create(
        self,
        *,
        film: str,
        watched_on: str | None = None,
        rating: float | None = None,
        review_text: str | None = None,
        review_spoilers: bool | None = None,
        tags: list[str] | None = None,
        rewatch: bool | None = None,
        liked: bool | None = None,
        comment_policy: str | None = None,
        privacy_policy: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        self._require_api()
        payload: dict[str, Any] = {"filmId": self._client.films._film_lid(film)}
        if watched_on is not None:
            payload["diaryDetails"] = {"diaryDate": watched_on}
            if rewatch is not None:
                payload["diaryDetails"]["rewatch"] = rewatch
        elif rewatch is not None:
            payload["diaryDetails"] = {"diaryDate": None, "rewatch": rewatch}
        if review_text is not None:
            payload["review"] = {"text": review_text}
            if review_spoilers is not None:
                payload["review"]["containsSpoilers"] = review_spoilers
        if tags is not None:
            payload["tags"] = tags
        if rating is not None:
            payload["rating"] = rating
        if liked is not None:
            payload["like"] = liked
        if comment_policy is not None:
            payload["commentPolicy"] = comment_policy
        if privacy_policy is not None:
            payload["privacyPolicy"] = privacy_policy
        payload.update(extra)
        return self.transport.request("POST", "/log-entries", api=True, json=payload, expected_status=(200, 201)).json()

    def update(
        self,
        log_entry: str,
        *,
        watched_on: str | None | object = _UNSET,
        remove_diary: bool = False,
        rating: float | None | object = _UNSET,
        review_text: str | None | object = _UNSET,
        remove_review: bool = False,
        review_spoilers: bool | None | object = _UNSET,
        tags: list[str] | None | object = _UNSET,
        liked: bool | None | object = _UNSET,
        comment_policy: str | None | object = _UNSET,
        privacy_policy: str | None | object = _UNSET,
        rewatch: bool | None | object = _UNSET,
        **extra: Any,
    ) -> dict[str, Any]:
        self._require_api()
        lid = self._log_lid(log_entry)
        payload: dict[str, Any] = {}
        if remove_diary:
            payload["diaryDetails"] = None
        elif watched_on is not _UNSET or rewatch is not _UNSET:
            diary_details: dict[str, Any] = {}
            if watched_on is not _UNSET:
                diary_details["diaryDate"] = watched_on
            if rewatch is not _UNSET:
                diary_details["rewatch"] = rewatch
            payload["diaryDetails"] = diary_details
        if remove_review:
            payload["review"] = None
        elif review_text is not _UNSET or review_spoilers is not _UNSET:
            review_payload: dict[str, Any] = {}
            if review_text is not _UNSET:
                review_payload["text"] = review_text
            if review_spoilers is not _UNSET:
                review_payload["containsSpoilers"] = review_spoilers
            payload["review"] = review_payload
        payload.update(
            _drop_unset(
                {
                    "tags": tags,
                    "rating": rating,
                    "like": liked,
                    "commentPolicy": comment_policy,
                    "privacyPolicy": privacy_policy,
                }
            )
        )
        payload.update(extra)
        return self.transport.request("PATCH", f"/log-entry/{lid}", api=True, json=payload, expected_status=(200,)).json()

    def delete(self, log_entry: str) -> None:
        self._require_api()
        lid = self._log_lid(log_entry)
        self.transport.request("DELETE", f"/log-entry/{lid}", api=True, expected_status=(204,))

    def comment(self, log_entry: str, text: str) -> dict[str, Any]:
        self._require_api()
        lid = self._log_lid(log_entry)
        return self.transport.request(
            "POST",
            f"/log-entry/{lid}/comments",
            api=True,
            json={"comment": text},
            expected_status=(200, 201),
        ).json()

    def like(self, log_entry: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._log_lid(log_entry)
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

    def _list_lid(self, list_id: str) -> str:
        if list_id.startswith("http") or list_id.startswith("/"):
            return self._require_lid(list_id)
        return self._require_lid(f"/{list_id.strip('/')}/")

    def list(self, member: str | None = None, filters: dict[str, Any] | None = None, cursor: str | None = None) -> Page[ListResource]:
        if member:
            member_url, _ = self._client.members._member_url(member)
            path = urlparse(member_url).path.rstrip("/") + "/lists/"
        else:
            path = "/lists/"
        html = self.transport.get_html(path, params={**(filters or {}), **({"cursor": cursor} if cursor else {})})
        items = [_list_from_result(result) for result in parse_search_results(self._client.base_url, html) if result.kind == "list"]
        return Page(
            items=items,
            next_cursor=extract_next_cursor_from_html(html),
            source_url=_ensure_page_url(path, self._client.base_url),
        )

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

    def create(
        self,
        *,
        name: str,
        published: bool = True,
        ranked: bool = False,
        description: str | None = None,
        comment_policy: str | None = None,
        share_policy: str | None = None,
        cloned_from: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        self._require_api()
        payload: dict[str, Any] = {"name": name, "published": published, "ranked": ranked}
        if description is not None:
            payload["description"] = description
        if comment_policy is not None:
            payload["commentPolicy"] = comment_policy
        if share_policy is not None:
            payload["sharePolicy"] = share_policy
        if cloned_from is not None:
            payload["clonedFrom"] = self._list_lid(cloned_from)
        payload.update(extra)
        return self.transport.request("POST", "/lists", api=True, json=payload, expected_status=(200, 201)).json()

    def update(
        self,
        list_id: str,
        *,
        version: int | None | object = _UNSET,
        published: bool | None | object = _UNSET,
        name: str | None | object = _UNSET,
        comment_policy: str | None | object = _UNSET,
        share_policy: str | None | object = _UNSET,
        ranked: bool | None | object = _UNSET,
        description: str | None | object = _UNSET,
        tags: list[str] | None | object = _UNSET,
        films_to_remove: list[str] | None | object = _UNSET,
        **extra: Any,
    ) -> dict[str, Any]:
        self._require_api()
        lid = self._list_lid(list_id)
        payload = _drop_unset(
            {
                "version": version,
                "published": published,
                "name": name,
                "commentPolicy": comment_policy,
                "sharePolicy": share_policy,
                "ranked": ranked,
                "description": description,
                "tags": tags,
                "filmsToRemove": [self._client.films._film_lid(film) for film in films_to_remove] if films_to_remove is not _UNSET and films_to_remove is not None else films_to_remove,
            }
        )
        payload.update(extra)
        return self.transport.request("PATCH", f"/list/{lid}", api=True, json=payload, expected_status=(200,)).json()

    def delete(self, list_id: str) -> None:
        self._require_api()
        lid = self._list_lid(list_id)
        self.transport.request("DELETE", f"/list/{lid}", api=True, expected_status=(204,))

    def upsert_entries(self, list_id: str, entries: list[dict[str, Any] | str]) -> dict[str, Any]:
        self._require_api()
        lid = self._list_lid(list_id)
        payload_entries: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, str):
                payload_entries.append({"film": self._client.films._film_lid(entry), "action": "ADD"})
                continue
            entry_payload = dict(entry)
            film_value = entry_payload.get("film")
            if film_value:
                entry_payload["film"] = self._client.films._film_lid(str(film_value))
            payload_entries.append(entry_payload)
        return self.transport.request(
            "PATCH",
            f"/list/{lid}",
            api=True,
            json={"entries": payload_entries},
            expected_status=(200,),
        ).json()

    def comment(self, list_id: str, text: str) -> dict[str, Any]:
        self._require_api()
        lid = self._list_lid(list_id)
        return self.transport.request(
            "POST",
            f"/list/{lid}/comments",
            api=True,
            json={"comment": text},
            expected_status=(200, 201),
        ).json()

    def like(self, list_id: str, enabled: bool = True) -> dict[str, Any]:
        self._require_api()
        lid = self._list_lid(list_id)
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
