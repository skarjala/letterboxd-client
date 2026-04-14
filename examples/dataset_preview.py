"""Preview a Letterboxd export dataset as normalized rows and a dataframe."""

from argparse import ArgumentParser
from pathlib import Path

from letterboxd_client import LetterboxdClient


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Preview a Letterboxd export dataset.")
    parser.add_argument(
        "archive",
        nargs="?",
        default="letterboxd-export.zip",
        help="Path to the export archive.",
    )
    parser.add_argument(
        "--dataset",
        default="diary_entries",
        help="Dataset key to preview. Falls back to diary if diary_entries is missing.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of rows to display.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = LetterboxdClient()
    archive = Path(args.archive)
    datasets = client.exports.load_account_export_zip(archive)

    print("Available datasets:")
    for name, rows in sorted(datasets.items()):
        print(f"- {name}: {len(rows)} rows")

    rows = datasets.get(args.dataset) or datasets.get("diary", [])
    if not rows:
        print(f"No rows found for {args.dataset!r}.")
        return

    normalized = client.exports.normalize(rows)
    print(f"\nNormalized preview for {args.dataset}:")
    for row in normalized[: args.limit]:
        print(row)

    try:
        frame = client.bulk.to_pandas(normalized)
    except ImportError:
        print("\nInstall pandas to view a dataframe preview.")
        return

    print("\nDataframe preview:")
    print(frame.head(args.limit).to_string(index=False))


if __name__ == "__main__":
    main()
