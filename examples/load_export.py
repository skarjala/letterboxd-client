"""Load a Letterboxd export archive and emit JSONL."""

from argparse import ArgumentParser

from pathlib import Path

from letterboxd_client import LetterboxdClient


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Load a Letterboxd export archive and print JSONL.")
    parser.add_argument(
        "archive",
        nargs="?",
        default="letterboxd-export.zip",
        help="Path to the export archive.",
    )
    parser.add_argument(
        "--dataset",
        default="diary_entries",
        help="Dataset key to print. Falls back to diary if diary_entries is missing.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of preview rows to print.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = LetterboxdClient()
    archive = Path(args.archive)
    datasets = client.exports.load_account_export_zip(archive)
    print("Available datasets:")
    for name, rows in sorted(datasets.items()):
        print(f"- {name}: {len(rows)} rows")

    selected = datasets.get(args.dataset) or datasets.get("diary", [])
    if not selected:
        print(f"No rows found for {args.dataset!r}.")
        return

    preview = client.exports.normalize(selected[: args.limit])
    print(f"\nJSONL preview for {args.dataset}:")
    print(client.exports.to_jsonl(preview))


if __name__ == "__main__":
    main()
