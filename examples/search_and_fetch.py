"""Search for a film and fetch its high-level metadata."""

from argparse import ArgumentParser

from letterboxd_client import LetterboxdClient


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Search Letterboxd and print the first film match.")
    parser.add_argument("query", nargs="?", default="parasite", help="Search text to look up.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = LetterboxdClient()
    results = client.search.search(args.query, kind="film")
    if not results:
        print("No results.")
        return
    film = client.films.get(results[0].url)
    print({"title": film.title, "year": film.year, "url": film.url})


if __name__ == "__main__":
    main()
