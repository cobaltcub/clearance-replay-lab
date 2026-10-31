"""Response classifier tests."""

import unittest

from botlab.probe import Outcome, classify


class ProbeTests(unittest.TestCase):
    def test_plain_200_is_ok(self):
        verdict = classify(200, {}, "<html><title>Hello</title></html>")
        self.assertEqual(verdict.outcome, Outcome.OK)

    def test_403_with_marker_is_challenge(self):
        verdict = classify(
            403,
            {"server": "cloudflare"},
            "<html><title>Just a moment...</title></html>",
        )
        self.assertEqual(verdict.outcome, Outcome.CHALLENGE)
        self.assertIn("just a moment", verdict.reason)

    def test_200_with_marker_is_still_challenge(self):
        verdict = classify(
            200,
            {},
            "<html>Enable JavaScript and cookies to continue</html>",
        )
        self.assertEqual(verdict.outcome, Outcome.CHALLENGE)

    def test_plain_403_is_blocked(self):
        verdict = classify(403, {}, "<html>Access denied</html>")
        self.assertEqual(verdict.outcome, Outcome.BLOCKED)

    def test_401_and_429_are_blocked(self):
        self.assertEqual(classify(401, {}, "").outcome, Outcome.BLOCKED)
        self.assertEqual(classify(429, {}, "").outcome, Outcome.BLOCKED)

    def test_5xx_is_error(self):
        self.assertEqual(classify(503, {}, "Service Unavailable").outcome, Outcome.ERROR)

    def test_unknown_status(self):
        self.assertEqual(classify(302, {}, "").outcome, Outcome.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
