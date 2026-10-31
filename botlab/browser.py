"""Acquire a browser session with Playwright.

This is the same broad approach as the original prototype, but it records the
full cookie jar and the final page state instead of only a name/value dump.
The stealth wrapper is kept because removing it would change the experiment;
it is not treated as a guarantee.
"""

from __future__ import annotations

import time

from .config import CLEARANCE_COOKIE_NAMES
from .probe import looks_like_challenge
from .session import Cookie, SessionData


class AcquisitionError(RuntimeError):
    pass


def _cookie_from_playwright(raw: dict) -> Cookie:
    expires = raw.get("expires")
    if expires is None or expires <= 0:
        expires = None
    return Cookie(
        name=str(raw.get("name", "")),
        value=str(raw.get("value", "")),
        domain=str(raw.get("domain", "") or ""),
        path=str(raw.get("path", "") or "/"),
        expires=float(expires) if expires is not None else None,
        secure=bool(raw.get("secure", False)),
        http_only=bool(raw.get("httpOnly", False)),
        same_site=raw.get("sameSite"),
    )


def _page_state(page) -> tuple[str, str]:
    try:
        return page.title(), page.content()
    except Exception:
        # Navigation can destroy the execution context between polls. The next
        # iteration will read the new document.
        return "", ""


def _user_agent(page) -> str:
    for _ in range(5):
        try:
            return str(page.evaluate("() => navigator.userAgent"))
        except Exception:
            try:
                page.wait_for_timeout(100)
            except Exception:
                break
    return ""


def acquire_session(
    url: str,
    *,
    headless: bool = True,
    timeout: float = 20.0,
    user_agent: str | None = None,
    clearance_names: tuple[str, ...] = CLEARANCE_COOKIE_NAMES,
) -> SessionData:
    """Open ``url`` in Chromium and return the session it ends up with.

    A challenge is considered solved when a clearance cookie exists and the
    final document no longer looks like a challenge page. If the page is simply
    unprotected, ``solved`` is also true; the cookie count tells the two cases
    apart.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise AcquisitionError(
            "playwright is not installed: pip install -r requirements.txt"
        ) from exc

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None

    manager = (
        Stealth().use_sync(sync_playwright()) if Stealth else sync_playwright()
    )

    navigation_error = ""
    browser = None
    try:
        with manager as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=user_agent,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded",
                          timeout=int(timeout * 1000))
            except Exception as exc:
                navigation_error = f"{type(exc).__name__}: {exc}"
                if page.url == "about:blank":
                    raise AcquisitionError(
                        f"could not open {url}: {navigation_error}"
                    ) from exc

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    cookies = context.cookies()
                except Exception:
                    cookies = []
                names = {str(cookie.get("name", "")) for cookie in cookies}
                title, body = _page_state(page)
                if names & set(clearance_names) and body and not looks_like_challenge(body):
                    break
                try:
                    page.wait_for_timeout(250)
                except Exception:
                    time.sleep(0.1)

            try:
                cookies = context.cookies()
            except Exception:
                cookies = []

            final_url = page.url
            title, body = _page_state(page)
            if not body:  # one short retry for a reload in progress
                try:
                    page.wait_for_timeout(250)
                except Exception:
                    pass
                title, body = _page_state(page)

            session = SessionData(
                user_agent=_user_agent(page),
                cookies=[_cookie_from_playwright(cookie) for cookie in cookies],
                source_url=url,
                final_url=final_url,
                title=title,
                solved=bool(body) and not looks_like_challenge(body),
                notes=(
                    f"engine=playwright-chromium stealth={Stealth is not None} "
                    f"headless={headless}"
                    + (f" navigation_error={navigation_error}" if navigation_error else "")
                ),
            )
            return session
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"browser session failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
