"""Bulk traversal and optional dataframe conversion utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from .models import Page, to_plain_data


def iterate_all(call: Callable[..., Page[Any]], *args: Any, cursor_arg: str = "cursor", **kwargs: Any) -> Iterator[Any]:
    cursor = kwargs.pop(cursor_arg, None)
    while True:
        page = call(*args, **kwargs, **({cursor_arg: cursor} if cursor else {}))
        yield from page.items
        if not page.next_cursor:
            break
        cursor = page.next_cursor


def flatten_pages(pages: Iterable[Page[Any]]) -> list[Any]:
    items: list[Any] = []
    for page in pages:
        items.extend(page.items)
    return items


def hydrate_many(ids: Iterable[str], getter: Callable[[str], Any]) -> list[Any]:
    return list(iter_hydrate_many(ids, getter))


def iter_hydrate_many(ids: Iterable[str], getter: Callable[[str], Any]) -> Iterator[Any]:
    for item_id in ids:
        yield getter(item_id)


def dedupe_by_lid(records: Iterable[dict[str, Any] | Any]) -> list[dict[str, Any] | Any]:
    seen: set[str] = set()
    deduped: list[dict[str, Any] | Any] = []
    for record in records:
        if isinstance(record, dict):
            key = str(record.get("id") or record.get("url") or record)
        else:
            plain = to_plain_data(record)
            key = str(plain.get("id") or plain.get("url") or plain)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _tabularise(data: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in data:
        plain = to_plain_data(item)
        if isinstance(plain, dict):
            rows.append(plain)
        else:
            rows.append({"value": plain})
    return rows


def to_pandas(data: Iterable[Any]) -> Any:
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise ImportError("Install the 'dataframes' extra to use pandas support") from exc
    return pd.DataFrame(_tabularise(data))


def to_polars(data: Iterable[Any]) -> Any:
    try:
        import polars as pl  # type: ignore
    except ImportError as exc:
        raise ImportError("Install the 'dataframes' extra to use polars support") from exc
    return pl.DataFrame(_tabularise(data))


def to_arrow(data: Iterable[Any]) -> Any:
    try:
        import pyarrow as pa  # type: ignore
    except ImportError as exc:
        raise ImportError("Install the 'dataframes' extra to use Arrow support") from exc
    return pa.Table.from_pylist(_tabularise(data))
