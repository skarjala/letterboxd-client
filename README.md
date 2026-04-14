# letterboxd-client

High-level Python SDK for Letterboxd ingestion, export parsing, and LLM/data-analysis workflows.

## What this project does

- Wraps Letterboxd with a high-level `LetterboxdClient`
- Supports public web reads, RSS ingestion, export parsing, and bulk traversal
- Keeps the public API ergonomic for analysis code instead of exposing raw endpoints
- Leaves destructive or fragile flows behind explicit authenticated methods

## Current status

This is an early scaffold focused on the MVP read/analysis surface:

- repo + package bootstrap
- transport and session plumbing
- typed models
- high-level client namespaces
- export parsing and JSONL output
- bulk iteration and dataframe adapters

Write methods are present, but most currently require a configured API bearer token because the public website mutation flows are not yet fully implemented.

## Install

```bash
conda run -p /Users/sandeepkarjala/pythonenv python -m pip install -e .
```

## Quickstart

```python
from letterboxd_client import LetterboxdClient

client = LetterboxdClient()

results = client.search.search("in the mood for love", kind="film")
first = results[0] if results else None

if first:
    film = client.films.get(first.url)
    print(film.title, film.year)
```

## Analysis examples

```python
from letterboxd_client import LetterboxdClient

client = LetterboxdClient()
export = client.exports.load_account_export_zip("letterboxd-export.zip")
diary = export.get("diary", [])
jsonl = client.exports.to_jsonl(diary)
print(jsonl.splitlines()[0])
```

```python
from letterboxd_client import LetterboxdClient

client = LetterboxdClient()
films = client.members.watchlist("some-member").items

try:
    frame = client.bulk.to_pandas(films)
    print(frame.head())
except ImportError:
    print("Install the dataframes extra for pandas/polars/arrow support.")
```

## SDK surface

- `client.auth`
- `client.search`
- `client.films`
- `client.members`
- `client.logs`
- `client.lists`
- `client.feeds`
- `client.exports`
- `client.bulk`
- `client.taxonomy`

## Examples

- [examples/load_export.py](examples/load_export.py)
- [examples/search_and_fetch.py](examples/search_and_fetch.py)

## Testing

```bash
conda run -p /Users/sandeepkarjala/pythonenv python -m unittest discover -s tests -v
```

