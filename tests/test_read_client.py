import unittest
from types import SimpleNamespace
from urllib.parse import urlencode, urlparse

from letterboxd_client.client import LetterboxdClient


def _build_url(path_or_url: str, params=None) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        base = path_or_url
    else:
        base = "https://letterboxd.com" + (
            path_or_url if path_or_url.startswith("/") else f"/{path_or_url.lstrip('/')}"
        )
    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def _infer_id(url: str) -> str | None:
    parts = [segment for segment in urlparse(url).path.split("/") if segment]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return parts[-1]


class FakeTransport:
    def __init__(self) -> None:
        self.base_url = "https://letterboxd.com"
        self.api_base = "https://api.letterboxd.com/api/v0"
        self.client = SimpleNamespace(headers={}, cookies=SimpleNamespace(clear=lambda: None))
        self._resolved = {
            "https://boxd.it/cure": "https://letterboxd.com/film/cure/",
        }
        self._pages = {
            "https://letterboxd.com/search/cure/": """
                <a href="/film/cure/" data-item-type="film" data-film-release-year="1997">Cure</a>
                <a href="/sandeepkarjala/" data-item-type="member">Sandeep Karjala</a>
            """,
            "https://letterboxd.com/film/cure/": """
                <html><head>
                  <meta property="og:title" content="Cure" />
                  <meta name="description" content="A hypnotic Japanese thriller." />
                  <script type="application/ld+json">
                    {"@type":"Movie","name":"Cure","datePublished":"1997-11-06","description":"A hypnotic Japanese thriller."}
                  </script>
                </head><body>
                  <p>Watched 567 Reviews 12</p>
                  <a href="/service/criterion-channel/">Criterion Channel</a>
                </body></html>
            """,
            "https://letterboxd.com/films/": """
                <a href="/film/cure/" data-item-type="film" data-film-release-year="1997">Cure</a>
                <a rel="next" href="/films/?cursor=films-next">Next</a>
            """,
            "https://letterboxd.com/sandeepkarjala/": """
                <html><head>
                  <meta property="og:title" content="Sandeep Karjala" />
                  <meta name="description" content="Logging films for analysis." />
                </head><body>
                  <p>Followers 321 Following 123 Reviews 67</p>
                </body></html>
            """,
            "https://letterboxd.com/sandeepkarjala/activity/": """
                <a href="/film/cure/">Cure</a>
                <a href="/list/top-japanese-thrillers/">Top Japanese Thrillers</a>
                <a rel="next" href="/sandeepkarjala/activity/?cursor=activity-next">Next</a>
            """,
            "https://letterboxd.com/sandeepkarjala/watchlist/": """
                <a href="/film/cure/" data-item-type="film" data-film-release-year="1997">Cure</a>
                <a rel="next" href="/sandeepkarjala/watchlist/?cursor=watchlist-next">Next</a>
            """,
            "https://letterboxd.com/sandeepkarjala/followers/": """
                <a href="/critic-a/" data-item-type="member">Critic A</a>
                <a rel="next" href="/sandeepkarjala/followers/?cursor=followers-next">Next</a>
            """,
            "https://letterboxd.com/sandeepkarjala/following/": """
                <a href="/critic-b/" data-item-type="member">Critic B</a>
                <a rel="next" href="/sandeepkarjala/following/?cursor=following-next">Next</a>
            """,
            "https://letterboxd.com/sandeepkarjala/films/diary/": """
                <a href="/log-entry/42/" data-item-type="log" data-film-name="Cure" data-film-id="cure" data-film-link="https://letterboxd.com/film/cure/" data-film-release-year="1997">Cure</a>
                <a rel="next" href="/sandeepkarjala/films/diary/?cursor=logs-next">Next</a>
            """,
            "https://letterboxd.com/log-entry/42/": """
                <html><head>
                  <meta name="description" content="This is a concise review of Cure." />
                </head><body>
                  <p>Likes 12 Comments 3</p>
                  <a href="/film/cure/" data-film-name="Cure" data-film-release-year="1997">Cure</a>
                  <article class="comment">
                    <a class="name" href="/critic-a/">Critic A</a>
                    <div class="comment-body">Great review</div>
                  </article>
                </body></html>
            """,
            "https://letterboxd.com/sandeepkarjala/lists/": """
                <a href="/list/top-japanese-thrillers/" data-item-type="list">Top Japanese Thrillers</a>
                <a rel="next" href="/sandeepkarjala/lists/?cursor=lists-next">Next</a>
            """,
            "https://letterboxd.com/list/top-japanese-thrillers/": """
                <html><head>
                  <meta property="og:title" content="Top Japanese Thrillers" />
                  <meta name="description" content="A compact list for parser tests." />
                </head><body>
                  <p>Likes 8 Comments 1</p>
                  <a href="/film/cure/" data-film-name="Cure" data-film-release-year="1997">Cure</a>
                  <article class="comment">
                    <a class="name" href="/critic-a/">Critic A</a>
                    <div class="comment-body">Nice list</div>
                  </article>
                </body></html>
            """,
            "https://letterboxd.com/sandeepkarjala/rss/": """
                <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
                  <channel>
                    <atom:link rel="next" href="https://letterboxd.com/sandeepkarjala/rss/?cursor=feed-next" />
                    <item>
                      <title>Cure was logged</title>
                      <link>https://letterboxd.com/film/cure/</link>
                      <description>Logged on a rainy evening.</description>
                    </item>
                  </channel>
                </rss>
            """,
            "https://letterboxd.com/films/genre/": """
                <a href="/films/genre/thriller/">Thriller</a>
                <a href="/films/genre/crime/">Crime</a>
                <a href="/films/genre/thriller/">Thriller</a>
            """,
        }

    def resolve_url(self, url_or_path: str) -> tuple[str, str | None]:
        resolved = self._resolved.get(url_or_path, _build_url(url_or_path))
        return resolved, _infer_id(resolved)

    def get_html(self, path: str, params=None, **kwargs):
        key = _build_url(path, params=params)
        try:
            return self._pages[key]
        except KeyError as exc:  # pragma: no cover - test guard
            raise AssertionError(f"Unexpected HTML request: {key}") from exc

    def get_json(self, path: str, *, api: bool = False, **kwargs):  # pragma: no cover - test guard
        raise AssertionError(f"Unexpected JSON request: {path!r}")

    def request(self, method: str, path: str, **kwargs):  # pragma: no cover - test guard
        raise AssertionError(f"Unexpected mutation request: {method} {path}")

    def close(self) -> None:
        pass


class ReadClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = LetterboxdClient(transport=FakeTransport())

    def test_search_and_films_expose_ids_and_cursors(self) -> None:
        results = self.client.search.search("cure")
        self.assertEqual(results[0].id, "cure")
        self.assertEqual(results[0].year, 1997)

        resolved = self.client.search.resolve("https://boxd.it/cure")
        self.assertEqual(resolved.title, "Cure")
        self.assertEqual(resolved.id, "cure")
        self.assertEqual(resolved.summary, "A hypnotic Japanese thriller.")

        films = self.client.films.list()
        self.assertEqual(films.next_cursor, "films-next")
        self.assertEqual(films.items[0].id, "cure")
        self.assertEqual(films.items[0].year, 1997)

    def test_member_pages_preserve_cursor_and_member_ids(self) -> None:
        activity = self.client.members.activity("sandeepkarjala")
        self.assertEqual(activity.next_cursor, "activity-next")
        self.assertEqual([item.kind for item in activity.items], ["film", "list"])

        watchlist = self.client.members.watchlist("sandeepkarjala")
        self.assertEqual(watchlist.next_cursor, "watchlist-next")
        self.assertEqual(watchlist.items[0].id, "cure")

        followers = self.client.members.followers("sandeepkarjala")
        self.assertEqual(followers.next_cursor, "followers-next")
        self.assertEqual(followers.items[0].id, "critic-a")

        following = self.client.members.following("sandeepkarjala")
        self.assertEqual(following.next_cursor, "following-next")
        self.assertEqual(following.items[0].username, "critic-b")

    def test_logs_lists_feeds_and_taxonomy_use_richer_parser_output(self) -> None:
        logs = self.client.logs.list(member="sandeepkarjala")
        self.assertEqual(logs.next_cursor, "logs-next")
        self.assertEqual(logs.items[0].id, "42")
        self.assertEqual(logs.items[0].film.title, "Cure")

        log_entry = self.client.logs.get("42")
        self.assertEqual(log_entry.review.text, "This is a concise review of Cure.")
        self.assertEqual(log_entry.comments[0].body, "Great review")

        lists = self.client.lists.list(member="sandeepkarjala")
        self.assertEqual(lists.next_cursor, "lists-next")
        self.assertEqual(lists.items[0].id, "top-japanese-thrillers")

        list_resource = self.client.lists.get("https://letterboxd.com/list/top-japanese-thrillers/")
        self.assertEqual(list_resource.entries[0].film.title, "Cure")
        self.assertEqual(self.client.lists.comments("https://letterboxd.com/list/top-japanese-thrillers/")[0].body, "Nice list")
        self.assertEqual(self.client.lists.stats("https://letterboxd.com/list/top-japanese-thrillers/")["likes"], 8)

        feed = self.client.feeds.member_rss("sandeepkarjala")
        self.assertEqual(feed.next_cursor, "feed-next")
        self.assertEqual(feed.items[0].target, "Cure was logged")

        self.assertEqual(self.client.taxonomy.genres(), ["Thriller", "Crime"])


if __name__ == "__main__":
    unittest.main()
