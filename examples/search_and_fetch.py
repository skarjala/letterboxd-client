"""Search for a film and fetch its high-level metadata."""

from letterboxd_client import LetterboxdClient


def main() -> None:
    client = LetterboxdClient()
    results = client.search.search("parasite", kind="film")
    if not results:
        print("No results.")
        return
    film = client.films.get(results[0].url)
    print({"title": film.title, "year": film.year, "url": film.url})


if __name__ == "__main__":
    main()

