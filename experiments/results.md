# Lab run — 2026-10-31 (UTC)

This is the output of one controlled run against the local challenge server.
The numbers are loopback timings, not internet timings.

## Environment

| Item | Value |
|---|---|
| Python | 3.11.4 |
| Platform | Windows 10.0.29698 |
| Playwright | 1.60.0 |
| curl_cffi | 0.15.0 |
| Browser | Chromium 148 (headless) |
| Lab TTL | 60 s |

Command:

```bash
python -m botlab experiment --headless --timeout 20 --json experiments/results.json
```

## Browser acquisition

| Measurement | Result |
|---|---|
| Solved | yes |
| Final title | `Protected content` |
| Clearance cookies | 1 |
| Acquisition time | 2.06 s |
| User-Agent | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ... Chrome/148.0.7778.96 Safari/537.36` |

## Replay matrix

| Case | Cookie | UA | Expected | HTTP | Outcome | Lab reason | Time |
|---|---|---|---|---|---|---|---|
| valid | valid | same | 200 ok | 200 | ok | ok | 2.8 ms |
| no_cookie | none | same | 403 challenge | 403 | challenge | missing | 1.5 ms |
| wrong_ua | valid | different | 403 challenge | 403 | challenge | bad-signature | 1.6 ms |
| tampered | modified | same | 403 challenge | 403 | challenge | bad-signature | 1.6 ms |
| expired | expired | same | 403 challenge | 403 | challenge | expired | 1.9 ms |

Expected outcomes matched: **5/5**.

## Observations

- The browser solved the lab challenge in about two seconds. Most of that is
  Chromium startup, not the challenge itself.
- The valid replay was a normal 200. The other four cases all returned the
  challenge page, but for different reasons. The `X-Lab-Reason` header made
  those reasons visible: missing cookie, UA mismatch, bad signature, expired
  token.
- The failure modes are not interchangeable. "Challenge" alone is a poor
  result; the useful data is why the session was rejected.
- Preserving the full cookie record was necessary for a clean replay. The
  original code's `{name: value}` dump would still have worked in this lab, but
  it loses the information needed to reason about domain/path/expiry.
- Replay time is dominated by local request overhead here; these numbers say
  nothing about real network latency.

## What this does not prove

- The lab uses a simple HMAC cookie, not Cloudflare's `cf_clearance`.
- There is no TLS/JA3 fingerprint check, IP binding, CAPTCHA, or behavioral
  analysis in the lab.
- One run on one machine is not a benchmark.
- A successful local replay does not imply a successful replay against a
  third-party target.

## What I would test next

1. Headless vs. headed acquisition on the same lab, repeated enough to see
   whether the browser mode affects acquisition time or cookie contents.
2. A second lab challenge that checks `Sec-Fetch-*` headers as well as the
   cookie, to see how much of the "browser context" matters.
3. A TTL sweep (1 s, 5 s, 30 s, 300 s) to measure replay success near expiry.
4. A real target, only with authorization, with the same matrix and raw logs.
