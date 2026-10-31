"""Session serialization tests."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from botlab.session import Cookie, SessionData


class SessionTests(unittest.TestCase):
    def test_cookie_roundtrip_keeps_attributes(self):
        cookie = Cookie(
            name="lab_clearance",
            value="123.abc",
            domain="127.0.0.1",
            path="/",
            expires=time.time() + 60,
            secure=True,
            http_only=True,
            same_site="Lax",
        )
        restored = Cookie.from_dict(cookie.to_dict())
        self.assertEqual(restored, cookie)

    def test_session_roundtrip(self):
        session = SessionData(
            user_agent="test-agent",
            cookies=[Cookie("lab_clearance", "abc", domain="127.0.0.1")],
            source_url="http://127.0.0.1/",
            solved=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session.save(path)
            restored = SessionData.load(path)
        self.assertEqual(restored.user_agent, "test-agent")
        self.assertEqual(len(restored.cookies), 1)
        self.assertTrue(restored.solved)
        self.assertEqual(len(restored.clearance_cookies), 1)

    def test_legacy_dict_format(self):
        data = json.loads(
            '{"user_agent": "old-ua", "cookies": {"cf_clearance": "old-value"}}'
        )
        session = SessionData.from_dict(data)
        self.assertEqual(session.user_agent, "old-ua")
        self.assertEqual(session.cookies[0].name, "cf_clearance")
        self.assertEqual(session.cookies[0].value, "old-value")

    def test_expiry(self):
        self.assertTrue(Cookie("a", "b", expires=time.time() - 1).expired)
        self.assertFalse(Cookie("a", "b", expires=time.time() + 60).expired)
        self.assertFalse(Cookie("a", "b").expired)


if __name__ == "__main__":
    unittest.main()
