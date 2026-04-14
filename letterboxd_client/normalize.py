"""Normalization helpers for CSV rows and scraped payloads."""

from __future__ import annotations

import re
from typing import Any


_KEY_RE = re.compile(r"[^a-z0-9]+")
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


def snake_case(value: str) -> str:
    value = value.strip().lower()
    return _KEY_RE.sub("_", value).strip("_")


def coerce_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped == "":
        return None
    lower = stripped.lower()
    if lower in _TRUE:
        return True
    if lower in _FALSE:
        return False
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped


def normalize_mapping(row: dict[str, Any]) -> dict[str, Any]:
    return {snake_case(key): coerce_scalar(value) for key, value in row.items()}


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_mapping(record) for record in records]

