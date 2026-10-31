"""Classify a response instead of guessing from a status code alone."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .config import CHALLENGE_MARKERS


class Outcome(str, Enum):
    OK = "ok"
    CHALLENGE = "challenge"
    BLOCKED = "blocked"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    reason: str


def challenge_marker(body: str) -> str | None:
    """Return the first challenge marker found in a page, if any."""
    text = (body or "")[:20_000].lower()
    for marker in CHALLENGE_MARKERS:
        if marker in text:
            return marker
    return None


def looks_like_challenge(body: str) -> bool:
    return challenge_marker(body) is not None


def classify(status: int, headers: Mapping[str, str], body: str) -> Verdict:
    """Turn an HTTP response into an outcome plus a short reason.

    The distinction matters: a 403 with a challenge page is not the same as a
    plain 403, and a 200 can still be a challenge page.
    """
    marker = challenge_marker(body)
    if marker:
        return Verdict(Outcome.CHALLENGE, f"challenge marker: {marker!r}")

    if status >= 500:
        return Verdict(Outcome.ERROR, f"http {status}")

    if status in (401, 403, 429):
        return Verdict(Outcome.BLOCKED, f"http {status}")

    if 200 <= status < 300:
        return Verdict(Outcome.OK, f"http {status}")

    return Verdict(Outcome.UNKNOWN, f"http {status}")
