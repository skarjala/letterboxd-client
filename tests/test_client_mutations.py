import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

from letterboxd_client.client import LetterboxdClient


@dataclass
class RecordedRequest:
    method: str
    path: str
    api: bool
    expected_status: tuple[int, ...]
    kwargs: dict


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class RecordingTransport:
    def __init__(self) -> None:
        self.base_url = "https://letterboxd.com"
        self.api_base = "https://api.letterboxd.com/api/v0"
        self.client = SimpleNamespace(headers={"Authorization": "Bearer token"}, cookies=SimpleNamespace(clear=lambda: None))
        self.requests: list[RecordedRequest] = []

    def resolve_url(self, url_or_path: str) -> tuple[str, str | None]:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            parsed = urlparse(url_or_path)
            path = parsed.path
            url = url_or_path
        else:
            path = url_or_path
            url = self.base_url.rstrip("/") + path if path.startswith("/") else self.base_url.rstrip("/") + "/" + path.lstrip("/")
        lid = None
        cleaned = path.rstrip("/")
        if cleaned:
            lid = cleaned.split("/")[-1]
        return url, lid

    def request(self, method: str, path: str, *, api: bool = False, expected_status: tuple[int, ...] = (200,), **kwargs):
        self.requests.append(RecordedRequest(method=method, path=path, api=api, expected_status=expected_status, kwargs=kwargs))
        status_code = 204 if method == "DELETE" else 200
        payload = {"ok": True, "method": method, "path": path, "json": kwargs.get("json"), "data": kwargs.get("data")}
        return FakeResponse(status_code=status_code, payload=payload)

    def get_html(self, path: str, **kwargs):  # pragma: no cover - not used in these tests
        raise AssertionError(f"Unexpected HTML request: {path!r}")

    def get_json(self, path: str, *, api: bool = False, **kwargs):  # pragma: no cover - not used in these tests
        raise AssertionError(f"Unexpected JSON request: {path!r}")

    def close(self) -> None:  # pragma: no cover - not used in these tests
        pass


class ClientMutationPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RecordingTransport()
        self.client = LetterboxdClient(transport=self.transport)

    def assert_last_request(self, method: str, path: str, *, api: bool = True, json_body=None, data_body=None, expected_status=None) -> None:
        self.assertTrue(self.transport.requests, "No request was recorded")
        recorded = self.transport.requests[-1]
        self.assertEqual(recorded.method, method)
        self.assertEqual(recorded.path, path)
        self.assertEqual(recorded.api, api)
        if expected_status is not None:
            self.assertEqual(recorded.expected_status, expected_status)
        self.assertEqual(recorded.kwargs.get("json"), json_body)
        self.assertEqual(recorded.kwargs.get("data"), data_body)

    def test_film_mutations_emit_expected_payloads(self) -> None:
        self.client.films.watchlist("cure", enabled=True)
        self.assert_last_request("PATCH", "/film/cure/me", json_body={"inWatchlist": True}, expected_status=(200,))

        self.client.films.rate("cure", rating=4.5)
        self.assert_last_request("PATCH", "/film/cure/me", json_body={"rating": 4.5}, expected_status=(200,))

        self.client.films.like("cure", enabled=False)
        self.assert_last_request("PATCH", "/film/cure/me", json_body={"liked": False}, expected_status=(200,))

        self.client.films.mark_watched("cure", watched=True)
        self.assert_last_request("PATCH", "/film/cure/me", json_body={"watched": True}, expected_status=(200,))

    def test_member_mutations_emit_expected_payloads(self) -> None:
        self.client.members.follow("sandeepkarjala", enabled=True)
        self.assert_last_request("PATCH", "/member/sandeepkarjala/me", json_body={"following": True}, expected_status=(200,))

        self.client.members.block("sandeepkarjala", enabled=False)
        self.assert_last_request("PATCH", "/member/sandeepkarjala/me", json_body={"blocking": False}, expected_status=(200,))

    def test_log_mutations_forward_payloads(self) -> None:
        self.client.logs.create(
            film="cure",
            watched_on="2026-04-13",
            rating=4.5,
            review_text="Great film",
            review_spoilers=False,
            tags=["japan", "thriller"],
            rewatch=True,
            liked=True,
            comment_policy="Anyone",
            privacy_policy="Friends",
        )
        self.assert_last_request(
            "POST",
            "/log-entries",
            json_body={
                "filmId": "cure",
                "diaryDetails": {"diaryDate": "2026-04-13", "rewatch": True},
                "review": {"text": "Great film", "containsSpoilers": False},
                "tags": ["japan", "thriller"],
                "rating": 4.5,
                "like": True,
                "commentPolicy": "Anyone",
                "privacyPolicy": "Friends",
            },
            expected_status=(200, 201),
        )

        self.client.logs.update(
            "42",
            watched_on="2026-04-14",
            rating=5.0,
            review_text="Even better on rewatch",
            review_spoilers=True,
            tags=["rewatch"],
            liked=False,
            comment_policy="Friends",
            privacy_policy="You",
            rewatch=False,
        )
        self.assert_last_request(
            "PATCH",
            "/log-entry/42",
            json_body={
                "diaryDetails": {"diaryDate": "2026-04-14", "rewatch": False},
                "review": {"text": "Even better on rewatch", "containsSpoilers": True},
                "tags": ["rewatch"],
                "rating": 5.0,
                "like": False,
                "commentPolicy": "Friends",
                "privacyPolicy": "You",
            },
            expected_status=(200,),
        )

        self.client.logs.comment("42", "Nice review")
        self.assert_last_request("POST", "/log-entry/42/comments", json_body={"comment": "Nice review"}, expected_status=(200, 201))

        self.client.logs.like("42", enabled=False)
        self.assert_last_request("PATCH", "/log-entry/42/me", json_body={"liked": False}, expected_status=(200,))

        self.client.logs.delete("42")
        self.assert_last_request("DELETE", "/log-entry/42", expected_status=(204,))

    def test_list_mutations_forward_payloads(self) -> None:
        self.client.lists.create(
            name="Watch later",
            description="Queue for analysis",
            published=False,
            ranked=True,
            comment_policy="Friends",
            share_policy="Anyone",
        )
        self.assert_last_request(
            "POST",
            "/lists",
            json_body={
                "name": "Watch later",
                "description": "Queue for analysis",
                "published": False,
                "ranked": True,
                "commentPolicy": "Friends",
                "sharePolicy": "Anyone",
            },
            expected_status=(200, 201),
        )

        self.client.lists.update(
            "top-japanese-thrillers",
            name="Top Japanese Thrillers",
            description="Updated description",
            published=True,
            ranked=False,
            comment_policy="Anyone",
            share_policy="Friends",
            tags=["crime"],
            films_to_remove=["cure"],
            version=3,
        )
        self.assert_last_request(
            "PATCH",
            "/list/top-japanese-thrillers",
            json_body={
                "version": 3,
                "published": True,
                "name": "Top Japanese Thrillers",
                "commentPolicy": "Anyone",
                "sharePolicy": "Friends",
                "ranked": False,
                "description": "Updated description",
                "tags": ["crime"],
                "filmsToRemove": ["cure"],
            },
            expected_status=(200,),
        )

        self.client.lists.upsert_entries(
            "top-japanese-thrillers",
            ["cure", {"film": "pulse", "newPosition": 1, "notes": "Move up", "action": "ADD"}],
        )
        self.assert_last_request(
            "PATCH",
            "/list/top-japanese-thrillers",
            json_body={
                "entries": [
                    {"film": "cure", "action": "ADD"},
                    {"film": "pulse", "newPosition": 1, "notes": "Move up", "action": "ADD"},
                ]
            },
            expected_status=(200,),
        )

        self.client.lists.comment("top-japanese-thrillers", "Nice list")
        self.assert_last_request("POST", "/list/top-japanese-thrillers/comments", json_body={"comment": "Nice list"}, expected_status=(200, 201))

        self.client.lists.like("top-japanese-thrillers", enabled=True)
        self.assert_last_request("PATCH", "/list/top-japanese-thrillers/me", json_body={"liked": True}, expected_status=(200,))

        self.client.lists.delete("top-japanese-thrillers")
        self.assert_last_request("DELETE", "/list/top-japanese-thrillers", expected_status=(204,))


if __name__ == "__main__":
    unittest.main()
