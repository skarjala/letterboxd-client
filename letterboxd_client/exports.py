"""Export readers and JSONL utilities."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .models import to_plain_data
from .normalize import normalize_mapping, normalize_records


def _read_csv_text(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [normalize_mapping(dict(row)) for row in reader]


def parse_letterboxd_csv(path: str | Path) -> list[dict[str, Any]]:
    return _read_csv_text(Path(path).read_text(encoding="utf-8"))


def parse_imdb_export(path: str | Path) -> list[dict[str, Any]]:
    return _read_csv_text(Path(path).read_text(encoding="utf-8-sig"))


def normalize(data: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize_records([dict(item) for item in data])


def load_account_export_zip(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with archive.open(name) as handle:
                text = handle.read().decode("utf-8-sig")
            results[Path(name).stem] = _read_csv_text(text)
    return results


def to_jsonl(data: Iterable[Any], path: str | Path | None = None) -> str:
    lines = [json.dumps(to_plain_data(item), ensure_ascii=True, sort_keys=True) for item in data]
    payload = "\n".join(lines)
    if path is not None:
        Path(path).write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    return payload

