"""HTTP transport and session helpers."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from .errors import AuthenticationError, NotFound, PermissionDenied, RateLimited, UnsupportedFlow
from .parsers import extract_form


class LetterboxdTransport:
    """Thin wrapper around an `httpx.Client` with Letterboxd-specific defaults."""

    def __init__(
        self,
        *,
        base_url: str = "https://letterboxd.com",
        api_base: str = "https://api.letterboxd.com/api/v0",
        api_bearer_token: str | None = None,
        timeout: float = 20.0,
        user_agent: str = "letterboxd-client/0.1.0",
        retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_base = api_base.rstrip("/")
        self.retries = retries
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        if api_bearer_token:
            self.set_api_token(api_bearer_token)

    def close(self) -> None:
        self.client.close()

    def set_api_token(self, token: str) -> None:
        self.client.headers["Authorization"] = f"Bearer {token}"

    def set_cookies(self, cookies: dict[str, str]) -> None:
        for key, value in cookies.items():
            self.client.cookies.set(key, value)

    def request(
        self,
        method: str,
        path: str,
        *,
        api: bool = False,
        expected_status: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> httpx.Response:
        base = self.api_base if api else self.base_url
        url = path if path.startswith("http") else urljoin(base + "/", path.lstrip("/"))
        last_response: httpx.Response | None = None
        for attempt in range(self.retries + 1):
            response = self.client.request(method, url, **kwargs)
            last_response = response
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                if attempt < self.retries:
                    time.sleep(retry_after)
                    continue
                raise RateLimited(f"Rate limited by {url}")
            if response.status_code in expected_status:
                return response
            if response.status_code == 401:
                raise AuthenticationError(f"Authentication failed for {url}")
            if response.status_code == 403:
                raise PermissionDenied(f"Permission denied for {url}")
            if response.status_code == 404:
                raise NotFound(f"Not found: {url}")
            if 500 <= response.status_code < 600 and attempt < self.retries:
                time.sleep(0.25 * (attempt + 1))
                continue
            response.raise_for_status()
        if last_response is None:
            raise RuntimeError("Request loop terminated without a response")
        return last_response

    def get_html(self, path: str, **kwargs: Any) -> str:
        return self.request("GET", path, expected_status=(200,), **kwargs).text

    def get_json(self, path: str, *, api: bool = False, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, api=api, expected_status=(200,), **kwargs).json()

    def head(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", path, expected_status=(200, 301, 302, 303, 307, 308), **kwargs)

    def resolve_url(self, url_or_path: str) -> tuple[str, str | None]:
        response = self.head(url_or_path)
        return str(response.url), response.headers.get("x-letterboxd-identifier")

    def login(self, username: str, password: str) -> None:
        sign_in_html = self.get_html("/settings/")
        action, form_values = extract_form(sign_in_html)
        if not action:
            raise UnsupportedFlow("Could not locate the Letterboxd sign-in form")

        username_field = next((key for key in form_values if "user" in key.lower()), "username")
        password_field = next((key for key in form_values if "pass" in key.lower()), "password")
        form_values[username_field] = username
        form_values[password_field] = password

        response = self.request(
            "POST",
            action,
            data=form_values,
            expected_status=(200, 302, 303),
        )
        if "Sign in to Letterboxd" in response.text and response.status_code == 200:
            raise AuthenticationError("Letterboxd rejected the supplied credentials")

