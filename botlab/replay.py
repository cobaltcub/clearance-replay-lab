"""Replay a stored session with curl_cffi."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import BASE_HEADERS
from .probe import Outcome, classify
from .session import SessionData


@dataclass(frozen=True)
class ReplayResult:
    outcome: Outcome
    status: int | None
    reason: str
    elapsed_ms: float
    final_url: str
    content_length: int
    body_snippet: str
    lab_reason: str = ""


def replay(
    session: SessionData,
    url: str,
    *,
    timeout: float = 15.0,
    impersonate: str = "chrome",
) -> ReplayResult:
    """Send one request using the stored cookies and User-Agent."""
    try:
        from curl_cffi import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "curl_cffi is not installed: pip install -r requirements.txt"
        ) from exc

    start = time.perf_counter()
    client = requests.Session(impersonate=impersonate)
    headers = dict(BASE_HEADERS)
    if session.user_agent:
        headers["User-Agent"] = session.user_agent
    client.headers.update(headers)

    for cookie in session.cookies:
        try:
            if cookie.domain:
                client.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain.lstrip("."),
                    path=cookie.path or "/",
                    secure=cookie.secure,
                )
            else:
                client.cookies.set(cookie.name, cookie.value, secure=cookie.secure)
        except Exception:
            # A malformed cookie should show up as a failed experiment, not
            # crash the whole run.
            continue

    try:
        response = client.get(url, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return ReplayResult(
            outcome=Outcome.ERROR,
            status=None,
            reason=f"{type(exc).__name__}: {exc}",
            elapsed_ms=elapsed,
            final_url="",
            content_length=0,
            body_snippet="",
        )

    elapsed = (time.perf_counter() - start) * 1000
    verdict = classify(response.status_code, dict(response.headers), response.text)
    snippet = " ".join(response.text[:200].split())
    return ReplayResult(
        outcome=verdict.outcome,
        status=response.status_code,
        reason=verdict.reason,
        elapsed_ms=elapsed,
        final_url=str(response.url),
        content_length=len(response.content),
        body_snippet=snippet,
        lab_reason=response.headers.get("X-Lab-Reason", ""),
    )
