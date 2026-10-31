"""Shared constants for the replay lab.

This project is intentionally scoped to controlled experiments: the default
target is a local challenge server, and the CLI refuses non-loopback targets
unless the caller explicitly marks them as authorized.
"""

from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_LAB_URL = "http://127.0.0.1:8765/"
DEFAULT_SESSION_PATH = "sessions/session.json"
DEFAULT_RESULTS_PATH = "experiments/results.json"

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Headers that are safe and common for a document request. The browser-derived
# User-Agent is added at runtime; curl_cffi supplies the TLS/HTTP2 fingerprint.
BASE_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

CLEARANCE_COOKIE_NAMES = ("cf_clearance", "lab_clearance")

# Deliberately specific strings. A normal page can mention Cloudflare without
# being a challenge; matching only these markers keeps the classifier honest.
CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-challenge",
    "challenge-platform",
    "enable javascript and cookies to continue",
    "attention required! | cloudflare",
    "verify you are human",
)


def is_loopback_url(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in LOOPBACK_HOSTS
