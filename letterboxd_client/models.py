"""Typed resource models used across the SDK."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    source_url: str | None = None
    total: int | None = None


@dataclass(slots=True)
class SearchResult:
    kind: str
    title: str
    url: str
    id: str | None = None
    year: int | None = None
    summary: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilmRelationship:
    watched: bool | None = None
    rated: bool | None = None
    liked: bool | None = None
    in_watchlist: bool | None = None
    rating: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemberRelationship:
    following: bool | None = None
    blocked: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Film:
    id: str | None
    title: str
    url: str
    year: int | None = None
    summary: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    relationship: FilmRelationship | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Member:
    id: str | None
    username: str
    url: str
    display_name: str | None = None
    bio: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    relationship: MemberRelationship | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiaryDetails:
    watched_on: str | None = None
    rewatch: bool | None = None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Review:
    text: str | None = None
    spoiler: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Comment:
    id: str | None
    author: str | None
    body: str
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LogEntry:
    id: str | None
    film: Film | None
    url: str
    rating: float | None = None
    diary: DiaryDetails | None = None
    review: Review | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    comments: list[Comment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ListEntry:
    film: Film
    rank: int | None = None
    note: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ListResource:
    id: str | None
    title: str
    url: str
    description: str | None = None
    entries: list[ListEntry] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Activity:
    kind: str
    actor: str | None
    target: str | None
    url: str | None = None
    summary: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def to_plain_data(value: Any) -> Any:
    """Recursively convert package models to JSON-serialisable data."""
    if is_dataclass(value):
        return {key: to_plain_data(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_plain_data(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    return value

