import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

from letterboxd_client.client import LetterboxdClient
from letterboxd_client.errors import UnsupportedFlow


@dataclass
class SubmittedForm:
    page_path: str
    action_contains: str
    updates: dict | None
    required_fields: tuple[str, ...]


class SessionTransport:
    def __init__(self) -> None:
        self.base_url = "https://letterboxd.com"
        self.api_base = "https://api.letterboxd.com/api/v0"
        self.client = SimpleNamespace(
            headers={},
            cookies=SimpleNamespace(clear=lambda: None),
        )
        self.submitted: list[SubmittedForm] = []

    def resolve_url(self, url_or_path: str) -> tuple[str, str | None]:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            parsed = urlparse(url_or_path)
            path = parsed.path
            url = url_or_path
        else:
            path = url_or_path
            url = self.base_url.rstrip("/") + (
                path if path.startswith("/") else f"/{path.lstrip('/')}"
            )
        lid = path.rstrip("/").split("/")[-1] if path.rstrip("/") else None
        return url, lid

    def has_api_token(self) -> bool:
        return False

    def has_session(self) -> bool:
        return True

    def submit_form(
        self,
        page_path: str,
        *,
        action_contains: str | None = None,
        required_fields: tuple[str, ...] = (),
        updates=None,
        expected_status=(200, 302, 303),
    ):
        payload = {key: str(value) for key, value in dict(updates or {}).items()}
        self.submitted.append(
            SubmittedForm(
                page_path=page_path,
                action_contains=action_contains or "",
                updates=payload,
                required_fields=required_fields,
            )
        )
        return SimpleNamespace(
            status_code=200,
            url=page_path,
            json=lambda: {
                "page_path": page_path,
                "action_contains": action_contains,
                "updates": payload,
            },
        )

    def close(self) -> None:
        pass


class ApiOnlyTransport(SessionTransport):
    def has_session(self) -> bool:
        return False


class SessionMutationTests(unittest.TestCase):
    def test_simple_session_mutations_use_page_forms(self) -> None:
        transport = SessionTransport()
        client = LetterboxdClient(transport=transport)

        client.films.watchlist("cure", enabled=True)
        client.films.rate("cure", rating=4.5)
        client.films.like("cure", enabled=False)
        client.films.mark_watched("cure", watched=True)
        client.members.follow("sandeepkarjala", enabled=True)
        client.members.block("sandeepkarjala", enabled=False)
        client.logs.comment("42", "Nice review")
        client.logs.like("42", enabled=False)
        client.logs.delete("42")
        client.lists.comment("top-japanese-thrillers", "Nice list")
        client.lists.like("top-japanese-thrillers", enabled=True)
        client.lists.delete("top-japanese-thrillers")

        self.assertEqual(
            transport.submitted,
            [
                SubmittedForm("https://letterboxd.com/film/cure/", "watchlist", {"inWatchlist": "true"}, ()),
                SubmittedForm("https://letterboxd.com/film/cure/", "rate", {"rating": "4.5"}, ()),
                SubmittedForm("https://letterboxd.com/film/cure/", "like", {"liked": "false"}, ()),
                SubmittedForm("https://letterboxd.com/film/cure/", "watched", {"watched": "true"}, ()),
                SubmittedForm("https://letterboxd.com/sandeepkarjala/", "follow", {"following": "true"}, ()),
                SubmittedForm("https://letterboxd.com/sandeepkarjala/", "block", {"blocking": "false"}, ()),
                SubmittedForm("https://letterboxd.com/log-entry/42/", "comment", {"comment": "Nice review"}, ()),
                SubmittedForm("https://letterboxd.com/log-entry/42/", "like", {"liked": "false"}, ()),
                SubmittedForm("https://letterboxd.com/log-entry/42/", "delete", {}, ()),
                SubmittedForm("https://letterboxd.com/top-japanese-thrillers/", "comment", {"comment": "Nice list"}, ()),
                SubmittedForm("https://letterboxd.com/top-japanese-thrillers/", "like", {"liked": "true"}, ()),
                SubmittedForm("https://letterboxd.com/top-japanese-thrillers/", "delete", {}, ()),
            ],
        )

    def test_complex_mutations_still_require_api_or_future_form_support(self) -> None:
        transport = ApiOnlyTransport()
        client = LetterboxdClient(transport=transport)

        with self.assertRaises(UnsupportedFlow):
            client.logs.create(film="cure")
        with self.assertRaises(UnsupportedFlow):
            client.lists.create(name="Watch later")


if __name__ == "__main__":
    unittest.main()
