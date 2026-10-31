"""Lab server tests: signed cookie, UA binding, tampering, expiry."""

import re
import time
import unittest
import urllib.error
import urllib.request

from botlab.lab import LabServer


class LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = LabServer(ttl=60, quiet=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.lab.stop()

    def _get(self, *, cookie: str | None = None, ua: str = "lab-test-agent"):
        request = urllib.request.Request(self.lab.url, headers={"User-Agent": ua})
        if cookie:
            request.add_header("Cookie", f"lab_clearance={cookie}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode(), dict(response.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), dict(exc.headers)

    def test_no_cookie_gets_challenge(self):
        status, body, headers = self._get()
        self.assertEqual(status, 403)
        self.assertIn("Just a moment...", body)
        self.assertEqual(headers.get("X-Lab-Reason"), "missing")

    def test_token_from_challenge_page_is_accepted(self):
        status, body, _ = self._get()
        self.assertEqual(status, 403)
        match = re.search(r"lab_clearance=([0-9]+\.[0-9a-f]+)", body)
        self.assertIsNotNone(match)
        status, body, headers = self._get(cookie=match.group(1))
        self.assertEqual(status, 200)
        self.assertIn("Protected content", body)
        self.assertEqual(headers.get("X-Lab-Reason"), "ok")

    def test_cookie_is_bound_to_user_agent(self):
        token = self.lab.state.token("lab-test-agent")
        status, _, headers = self._get(cookie=token, ua="different-agent")
        self.assertEqual(status, 403)
        self.assertEqual(headers.get("X-Lab-Reason"), "bad-signature")

    def test_tampered_cookie_is_rejected(self):
        token = self.lab.state.token("lab-test-agent")
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        status, _, headers = self._get(cookie=tampered)
        self.assertEqual(status, 403)
        self.assertEqual(headers.get("X-Lab-Reason"), "bad-signature")

    def test_expired_cookie_is_rejected(self):
        issued = time.time() - self.lab.state.ttl - 10
        token = self.lab.state.token("lab-test-agent", issued_at=issued)
        status, _, headers = self._get(cookie=token)
        self.assertEqual(status, 403)
        self.assertEqual(headers.get("X-Lab-Reason"), "expired")


if __name__ == "__main__":
    unittest.main()
