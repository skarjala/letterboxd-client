"""Load a Letterboxd export archive and emit JSONL."""

from pathlib import Path

from letterboxd_client import LetterboxdClient


def main() -> None:
    client = LetterboxdClient()
    archive = Path("letterboxd-export.zip")
    datasets = client.exports.load_account_export_zip(archive)
    diary_rows = datasets.get("diary", [])
    jsonl = client.exports.to_jsonl(diary_rows)
    print(jsonl[:500])


if __name__ == "__main__":
    main()

