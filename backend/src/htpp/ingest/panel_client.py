"""Read-only panel client. Path allowlist and a global rate limit are enforced."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

from htpp.config import ROOT, settings

log = logging.getLogger("htpp.panel")

ALLOWED_PATHS = frozenset({
    "/graph.php",
    "/dashboard.php",
    "/alltsgraph3.php",
    "/currentDataView.php",
    "/currentDataView2.php",
    "/downloaddata.php",
})
FORBIDDEN_PATHS = frozenset({
    "/config.php",
    "/configstatus.php",
    "/changeBatch.php",
    "/changeBatchTiming.php",
    "/addMobile.php",
    "/logout.php",
})

USER_AGENT = (
    "HTPP-DigitalShadow/1.0 research crawler; 1 req/2s read-only"
)


class ForbiddenPathError(RuntimeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Refusing to request non-allowlisted path {path}")
        self.path = path


class AsyncRateLimiter:
    def __init__(self, min_interval_s: float) -> None:
        self.min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def __aenter__(self) -> None:
        async with self._lock:
            wait = self._next - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next = time.monotonic() + self.min_interval_s

    async def __aexit__(self, *args: object) -> None:
        return None


class PanelClient:
    def __init__(self) -> None:
        self._limiter = AsyncRateLimiter(settings.request_min_interval_s)
        cookie_path = ROOT / "data" / ".panel_cookies.txt"
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._cookie_path = cookie_path
        self._client = httpx.AsyncClient(
            base_url=settings.panel_base_url.rstrip("/"),
            timeout=settings.request_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self._load_cookies()

    def _load_cookies(self) -> None:
        if settings.session_cookie:
            self._client.cookies.set("PHPSESSID", settings.session_cookie)
        if not self._cookie_path.exists():
            return
        for line in self._cookie_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            name, value = line.split("=", 1)
            if name and value:
                self._client.cookies.set(name, value)

    def _save_cookies(self) -> None:
        lines = [f"{cookie.name}={cookie.value}" for cookie in self._client.cookies.jar]
        self._cookie_path.write_text("\n".join(lines), encoding="utf-8")

    async def aclose(self) -> None:
        self._save_cookies()
        await self._client.aclose()

    async def login(self) -> None:
        if not settings.panel_username or not settings.panel_password:
            raise RuntimeError("Panel credentials are missing from the environment")
        async with self._limiter:
            page = await self._client.get("/login.php")
        form = _login_fields(page.text)
        payload = {
            form["username"]: settings.panel_username,
            form["password"]: settings.panel_password,
        }
        if form.get("submit_name"):
            payload[form["submit_name"]] = form.get("submit_value") or "1"
        async with self._limiter:
            response = await self._client.post(form["action"], data=payload)
        response.raise_for_status()
        if _looks_like_login_page(response.text) and "incorrect" in response.text.lower():
            raise RuntimeError("Panel login was rejected")
        self._save_cookies()
        log.info("panel session established")

    async def is_authenticated(self) -> bool:
        async with self._limiter:
            response = await self._client.get("/dashboard.php", params={"machineid": settings.machine_ids[0]})
        return not _looks_like_login_page(response.text)

    async def get(self, path: str, params: dict | None = None) -> str:
        if path in FORBIDDEN_PATHS or path not in ALLOWED_PATHS:
            raise ForbiddenPathError(path)
        async with self._limiter:
            response = await self._client.get(path, params=params)
        if _looks_like_login_page(response.text):
            await self.login()
            async with self._limiter:
                response = await self._client.get(path, params=params)
            if _looks_like_login_page(response.text):
                raise RuntimeError("Panel session expired and re-login did not stick")
        response.raise_for_status()
        return response.text


def _looks_like_login_page(html: str) -> bool:
    lowered = html.lower()
    return 'id="loginform"' in lowered or ("name=\"password\"" in lowered and "btn-login" in lowered)


def _login_fields(html: str) -> dict[str, str]:
    tree = HTMLParser(html)
    form = tree.css_first("form")
    if form is None:
        raise RuntimeError("Login page has no form")
    action = form.attributes.get("action") or "/login.php"
    if not action.startswith("/"):
        action = "/" + action
    username = password = None
    submit_name = submit_value = None
    for node in form.css("input, button"):
        name = node.attributes.get("name")
        kind = (node.attributes.get("type") or "").lower()
        if kind == "password" and name:
            password = name
        elif kind in {"text", "email"} and name and username is None:
            username = name
        elif kind == "submit" or node.tag == "button":
            if name:
                submit_name = name
                submit_value = node.attributes.get("value") or "1"
    if not username or not password:
        raise RuntimeError("Could not discover login field names from the form")
    return {
        "action": action,
        "username": username,
        "password": password,
        "submit_name": submit_name or "",
        "submit_value": submit_value or "",
    }
