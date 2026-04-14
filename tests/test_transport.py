import unittest
from urllib.parse import parse_qs
from unittest.mock import call, patch

import httpx

from letterboxd_client.errors import AuthenticationError, NotFound, PermissionDenied, RateLimited, UnsupportedFlow
from letterboxd_client.transport import LetterboxdTransport


SIGN_IN_FORM = """
<html>
  <body>
    <form action="/session/" method="post">
      <input type="hidden" name="csrf_token" value="token-123">
      <input type="text" name="user_login" value="">
      <input type="password" name="user_password" value="">
    </form>
  </body>
</html>
"""

PAGE_FORMS = """
<html>
  <body>
    <form action="/film/cure/watchlist/" method="post">
      <input type="hidden" name="csrf" value="token-123">
      <input type="hidden" name="inWatchlist" value="false">
    </form>
    <form action="/film/cure/comments/" method="post">
      <input type="hidden" name="csrf" value="token-123">
      <textarea name="comment"></textarea>
    </form>
  </body>
</html>
"""

PAGE_FORMS_WITH_RELATIVE_ACTION = """
<html>
  <body>
    <form action="comments/" method="post">
      <input type="hidden" name="csrf" value="token-123">
      <textarea name="comment"></textarea>
    </form>
  </body>
</html>
"""


class TransportTests(unittest.TestCase):
    def make_transport(self, handler, retries: int = 1) -> LetterboxdTransport:
        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
            headers={"User-Agent": "test-agent"},
        )
        return LetterboxdTransport(client=client, retries=retries)

    def test_request_retries_request_error_then_succeeds(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                raise httpx.ConnectError("temporary failure", request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = self.make_transport(handler, retries=1)
        with patch("letterboxd_client.transport.time.sleep") as sleep:
            self.assertEqual(transport.get_html("/health"), "ok")

        self.assertEqual(calls["count"], 2)
        sleep.assert_called_once_with(0.25)

    def test_request_retries_5xx_then_succeeds(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(503, text="busy", request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = self.make_transport(handler, retries=1)
        with patch("letterboxd_client.transport.time.sleep") as sleep:
            self.assertEqual(transport.get_html("/health"), "ok")

        self.assertEqual(calls["count"], 2)
        sleep.assert_called_once_with(0.25)

    def test_request_retries_429_then_succeeds(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "1.5"}, request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = self.make_transport(handler, retries=1)
        with patch("letterboxd_client.transport.time.sleep") as sleep:
            self.assertEqual(transport.get_html("/health"), "ok")

        self.assertEqual(calls["count"], 2)
        sleep.assert_called_once_with(1.5)

    def test_request_maps_auth_and_lookup_statuses(self) -> None:
        for status_code, expected_error in (
            (401, AuthenticationError),
            (403, PermissionDenied),
            (404, NotFound),
        ):
            with self.subTest(status_code=status_code):
                transport = self.make_transport(
                    lambda request, status_code=status_code: httpx.Response(
                        status_code,
                        text="failure",
                        request=request,
                    )
                )
                with self.assertRaises(expected_error):
                    transport.get_html("/resource")

    def test_request_raises_rate_limited_after_retries(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0.5"}, request=request)

        transport = self.make_transport(handler, retries=1)
        with patch("letterboxd_client.transport.time.sleep") as sleep:
            with self.assertRaises(RateLimited):
                transport.get_html("/resource")

        self.assertEqual(sleep.call_args_list, [call(0.5)])

    def test_request_raises_unsupported_flow_after_retries(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="busy", request=request)

        transport = self.make_transport(handler, retries=1)
        with patch("letterboxd_client.transport.time.sleep") as sleep:
            with self.assertRaises(UnsupportedFlow):
                transport.get_html("/resource")

        self.assertEqual(sleep.call_args_list, [call(0.25)])

    def test_login_posts_hidden_inputs_and_manages_session_cookies(self) -> None:
        seen_bodies: list[dict[str, list[str]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/settings/":
                return httpx.Response(200, text=SIGN_IN_FORM, request=request)
            if request.method == "POST" and request.url.path == "/session/":
                seen_bodies.append(parse_qs(request.content.decode()))
                return httpx.Response(
                    200,
                    text="<html><body>Welcome back</body></html>",
                    headers={"Set-Cookie": "sessionid=abc123; Path=/; HttpOnly"},
                    request=request,
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        transport = self.make_transport(handler, retries=1)
        transport.set_api_token("api-token")

        transport.login("sandeep", "secret")

        self.assertEqual(seen_bodies, [{"csrf_token": ["token-123"], "user_login": ["sandeep"], "user_password": ["secret"]}])
        self.assertEqual(transport.get_cookies(), {"sessionid": "abc123"})
        self.assertIn("Authorization", transport.client.headers)

        transport.clear_session()
        self.assertEqual(transport.get_cookies(), {})
        self.assertNotIn("Authorization", transport.client.headers)

    def test_login_rejects_reused_sign_in_page(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/settings/":
                return httpx.Response(200, text=SIGN_IN_FORM, request=request)
            if request.method == "POST" and request.url.path == "/session/":
                return httpx.Response(200, text="Sign in to Letterboxd", request=request)
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        transport = self.make_transport(handler, retries=1)

        with self.assertRaises(AuthenticationError):
            transport.login("sandeep", "wrong-password")

    def test_submit_form_preserves_hidden_inputs_and_referer(self) -> None:
        seen_bodies: list[dict[str, list[str]]] = []
        seen_referers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/film/cure/":
                return httpx.Response(200, text=PAGE_FORMS, request=request)
            if request.method == "POST" and request.url.path == "/film/cure/comments/":
                seen_bodies.append(parse_qs(request.content.decode()))
                seen_referers.append(request.headers.get("referer"))
                return httpx.Response(200, text="ok", request=request)
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        transport = self.make_transport(handler, retries=1)

        response = transport.submit_form(
            "/film/cure/",
            action_contains="comments",
            updates={"comment": "Great review"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            seen_bodies,
            [{"csrf": ["token-123"], "comment": ["Great review"]}],
        )
        self.assertEqual(seen_referers, ["https://letterboxd.com/film/cure/"])

    def test_submit_form_resolves_relative_actions_from_page_url(self) -> None:
        seen_bodies: list[dict[str, list[str]]] = []
        seen_referers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/film/cure/":
                return httpx.Response(200, text=PAGE_FORMS_WITH_RELATIVE_ACTION, request=request)
            if request.method == "POST" and request.url.path == "/film/cure/comments/":
                seen_bodies.append(parse_qs(request.content.decode()))
                seen_referers.append(request.headers.get("referer"))
                return httpx.Response(200, text="ok", request=request)
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        transport = self.make_transport(handler, retries=1)

        response = transport.submit_form(
            "/film/cure/",
            action_contains="comments",
            updates={"comment": "Relative action"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            seen_bodies,
            [{"csrf": ["token-123"], "comment": ["Relative action"]}],
        )
        self.assertEqual(seen_referers, ["https://letterboxd.com/film/cure/"])


if __name__ == "__main__":
    unittest.main()
