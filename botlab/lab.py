"""A local, deliberately small anti-bot challenge.

The point is not to imitate Cloudflare. The point is to create a target where
the expected answer is known: a signed cookie, bound to the User-Agent, with an
expiry. That makes it possible to test replay behaviour without touching a
third-party site.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .session import Cookie

COOKIE_NAME = "lab_clearance"


class LabState:
    def __init__(self, ttl: float = 60.0, secret: bytes | None = None):
        self.ttl = ttl
        self.secret = secret or secrets.token_bytes(16)

    def _sign(self, expires: int, user_agent: str) -> str:
        message = f"{expires}|{user_agent}".encode("utf-8")
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()[:32]

    def token(self, user_agent: str, issued_at: float | None = None) -> str:
        issued = time.time() if issued_at is None else issued_at
        expires = int(issued + self.ttl)
        return f"{expires}.{self._sign(expires, user_agent)}"

    def verify(self, token: str, user_agent: str) -> tuple[bool, str]:
        try:
            expires_raw, signature = token.split(".", 1)
            expires = int(expires_raw)
        except (ValueError, AttributeError):
            return False, "malformed"

        if expires <= time.time():
            return False, "expired"

        expected = self._sign(expires, user_agent)
        if not hmac.compare_digest(signature, expected):
            return False, "bad-signature"

        return True, "ok"


def _challenge_page(token: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Just a moment...</title>
</head>
<body>
  <h1>Checking your browser</h1>
  <p>This is a local lab challenge, not a real Cloudflare page.</p>
  <p>It sets a signed cookie after a short delay, then reloads.</p>
  <script>
    setTimeout(function () {{
      document.cookie = "{COOKIE_NAME}={token}; path=/; SameSite=Lax";
      location.reload();
    }}, 700);
  </script>
</body>
</html>"""


def _protected_page() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Protected content</title></head>
<body>
  <h1>Protected content</h1>
  <p>The signed lab_clearance cookie was accepted for this User-Agent.</p>
</body>
</html>"""


def make_handler(state: LabState, quiet: bool = True):
    class Handler(BaseHTTPRequestHandler):
        server_version = "botlab/1.0"

        def log_message(self, fmt, *args):
            if not quiet:
                super().log_message(fmt, *args)

        def _send(self, status: int, body: str, reason: str | None = None) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            if reason:
                self.send_header("X-Lab-Reason", reason)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlparse(self.path).path
            user_agent = self.headers.get("User-Agent", "")

            if path == "/health":
                self._send(200, "ok")
                return

            if path == "/echo":
                body = json.dumps({
                    "user_agent": user_agent,
                    "cookie": self.headers.get("Cookie", ""),
                })
                self._send(200, body)
                return

            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                pass
            morsel = jar.get(COOKIE_NAME)
            token = morsel.value if morsel else ""

            if not token:
                self._send(403, _challenge_page(state.token(user_agent)), "missing")
                return

            valid, reason = state.verify(token, user_agent)
            if not valid:
                self._send(403, _challenge_page(state.token(user_agent)), reason)
                return

            self._send(200, _protected_page(), "ok")

    return Handler


class LabServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        ttl: float = 60.0,
        quiet: bool = True,
    ):
        self.state = LabState(ttl=ttl)
        self.httpd = ThreadingHTTPServer((host, port), make_handler(self.state, quiet))
        self.httpd.daemon_threads = True
        self.thread: threading.Thread | None = None
        self._host = host

    @property
    def url(self) -> str:
        port = self.httpd.server_address[1]
        return f"http://{self._host}:{port}/"

    def start(self) -> "LabServer":
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=2)

    def expired_cookie(self, user_agent: str) -> Cookie:
        """A cookie whose signed expiry is already in the past.

        The Cookie object has no ``expires`` attribute, so the HTTP client
        still sends it; the server is what rejects it. That keeps the test
        focused on the server-side check.
        """
        issued = time.time() - self.state.ttl - 10
        return Cookie(
            name=COOKIE_NAME,
            value=self.state.token(user_agent, issued_at=issued),
            domain="127.0.0.1",
            path="/",
        )

    def __enter__(self) -> "LabServer":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local replay lab challenge.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ttl", type=float, default=60.0,
                        help="clearance lifetime in seconds (default: 60)")
    args = parser.parse_args(argv)

    server = LabServer(args.host, args.port, args.ttl, quiet=False)
    print(f"[*] lab server: {server.url}")
    print(f"[*] clearance TTL: {args.ttl:.0f}s")
    print("[*] Ctrl+C to stop")
    try:
        server.httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] stopped")
    finally:
        server.httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
