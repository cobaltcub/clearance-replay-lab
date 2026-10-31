"""Replay tests against the local lab (no browser needed)."""

import unittest

from botlab.lab import LabServer
from botlab.probe import Outcome
from botlab.replay import replay
from botlab.session import Cookie, SessionData


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.lab = LabServer(ttl=60, quiet=True).start()
        self.ua = "replay-test-agent"
        self.session = SessionData(
            user_agent=self.ua,
            cookies=[
                Cookie(
                    name="lab_clearance",
                    value=self.lab.state.token(self.ua),
                    domain="127.0.0.1",
                    path="/",
                )
            ],
        )

    def tearDown(self):
        self.lab.stop()

    def test_valid_session_is_ok(self):
        result = replay(self.session, self.lab.url, timeout=5)
        self.assertEqual(result.outcome, Outcome.OK)
        self.assertEqual(result.status, 200)

    def test_missing_cookie_is_challenge(self):
        session = SessionData(user_agent=self.ua, cookies=[])
        result = replay(session, self.lab.url, timeout=5)
        self.assertEqual(result.outcome, Outcome.CHALLENGE)
        self.assertEqual(result.status, 403)

    def test_wrong_user_agent_is_challenge(self):
        session = SessionData(
            user_agent="different-agent",
            cookies=self.session.cookies,
        )
        result = replay(session, self.lab.url, timeout=5)
        self.assertEqual(result.outcome, Outcome.CHALLENGE)
        self.assertEqual(result.status, 403)


if __name__ == "__main__":
    unittest.main()
