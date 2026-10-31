"""Session and cookie storage.

The original prototype saved ``{name: value}`` and threw away the cookie
attributes. That is enough for a toy request but not enough to reason about
domain/path/expiry behaviour, so this version keeps the full record and can
still read the old format.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CLEARANCE_COOKIE_NAMES

SCHEMA_VERSION = 2


@dataclass
class Cookie:
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: float | None = None
    secure: bool = False
    http_only: bool = False
    same_site: str | None = None

    @property
    def expired(self) -> bool:
        return self.expires is not None and self.expires <= time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "secure": self.secure,
            "http_only": self.http_only,
            "same_site": self.same_site,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Cookie":
        expires = data.get("expires")
        if expires in (-1, None):
            expires = None
        return cls(
            name=str(data.get("name", "")),
            value=str(data.get("value", "")),
            domain=str(data.get("domain", "") or ""),
            path=str(data.get("path", "") or "/"),
            expires=float(expires) if expires is not None else None,
            secure=bool(data.get("secure", False)),
            http_only=bool(data.get("http_only", data.get("httpOnly", False))),
            same_site=data.get("same_site", data.get("sameSite")),
        )


@dataclass
class SessionData:
    user_agent: str
    cookies: list[Cookie] = field(default_factory=list)
    source_url: str = ""
    final_url: str = ""
    title: str = ""
    solved: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    notes: str = ""

    @property
    def clearance_cookies(self) -> list[Cookie]:
        return [c for c in self.cookies if c.name in CLEARANCE_COOKIE_NAMES]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "created_at": self.created_at,
            "source_url": self.source_url,
            "final_url": self.final_url,
            "title": self.title,
            "solved": self.solved,
            "user_agent": self.user_agent,
            "notes": self.notes,
            "cookies": [cookie.to_dict() for cookie in self.cookies],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        raw_cookies = data.get("cookies", [])
        if isinstance(raw_cookies, dict):  # legacy prototype format
            cookies = [
                Cookie(name=str(name), value=str(value))
                for name, value in raw_cookies.items()
            ]
        else:
            cookies = [Cookie.from_dict(cookie) for cookie in raw_cookies]

        return cls(
            user_agent=str(data.get("user_agent", "")),
            cookies=cookies,
            source_url=str(data.get("source_url", "")),
            final_url=str(data.get("final_url", "")),
            title=str(data.get("title", "")),
            solved=bool(data.get("solved", False)),
            created_at=str(data.get("created_at", "")),
            notes=str(data.get("notes", "")),
        )

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "SessionData":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
