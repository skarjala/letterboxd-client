"""HTTP transport and session helpers."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

import httpx

from .errors import AuthenticationError, NotFound, PermissionDenied, RateLimited, UnsupportedFlow
from .parsers import extract_form, extract_forms


def _retry_after_seconds(value: str | None) -> float:
    if not value:
        return 1.0
    try:
        return max(float(value), 0.0)
    except ValueError:
        return 1.0


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

    def set_cookies(self, cookies: Mapping[str, str]) -> None:
        self.client.cookies.clear()
        for key, value in cookies.items():
            self.client.cookies.set(key, value)

    def get_cookies(self) -> dict[str, str]:
        return dict(self.client.cookies.items())

    def clear_session(self) -> None:
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)

    def has_api_token(self) -> bool:
        return "Authorization" in self.client.headers

    def has_session(self) -> bool:
        return bool(self.get_cookies())

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
        for attempt in range(self.retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.RequestError as exc:
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise UnsupportedFlow(f"Request to {url} failed: {exc}") from exc

            if response.status_code in expected_status:
                return response
            if response.status_code == 401:
                raise AuthenticationError(f"Authentication failed for {url}")
            if response.status_code == 403:
                raise PermissionDenied(f"Permission denied for {url}")
            if response.status_code == 404:
                raise NotFound(f"Not found: {url}")
            if response.status_code == 429:
                if attempt < self.retries:
                    time.sleep(_retry_after_seconds(response.headers.get("Retry-After")))
                    continue
                raise RateLimited(f"Rate limited by {url}")
            if 500 <= response.status_code < 600:
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise UnsupportedFlow(f"Upstream service error ({response.status_code}) for {url}")
            raise UnsupportedFlow(f"Unexpected response ({response.status_code}) for {url}")

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

    def submit_form(
        self,
        page_path: str,
        *,
        action_contains: str | None = None,
        required_fields: tuple[str, ...] = (),
        updates: Mapping[str, Any] | None = None,
        expected_status: tuple[int, ...] = (200, 302, 303),
    ) -> httpx.Response:
        page_url = page_path if page_path.startswith("http") else urljoin(self.base_url + "/", page_path.lstrip("/"))
        html = self.get_html(page_url)
        forms = extract_forms(html)
        selected_form = None
        for form in forms:
            action = form.get("action") or page_url
            inputs = form.get("inputs", {})
            if action_contains and action_contains not in action:
                continue
            if required_fields and not all(field in inputs for field in required_fields):
                continue
            selected_form = form
            break
        if selected_form is None:
            raise UnsupportedFlow(f"Could not locate a matching form on {page_url}")

        payload = dict(selected_form.get("inputs", {}))
        if updates:
            for key, value in updates.items():
                payload[key] = str(value)

        return self.request(
            "POST",
            selected_form.get("action") or page_url,
            data=payload,
            headers={"Referer": page_url},
            expected_status=expected_status,
        )
