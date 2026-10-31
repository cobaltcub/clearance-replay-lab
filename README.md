# Clearance-cookie replay lab

> This started as `Anti-Bot-Bypass-Engine-`. It is no longer a bypass engine;
> it is a controlled lab for one question: can a browser-issued clearance
> cookie be replayed by a non-browser HTTP client?

I started with a "Cloudflare bypass" scraper. This is what it became after I
tried to make the claims testable.

## What I tried first

The first version did this:

1. Launch Chromium through Playwright + `playwright-stealth`.
2. Wait for a `cf_clearance` cookie.
3. Save the cookie name/value and the browser User-Agent to JSON.
4. Replay the request with `curl_cffi` using Chrome TLS impersonation.
5. If the response looked like a challenge, refresh the cookie and retry.

It looked like a bypass engine. It was not a good experiment:

- The default target was `example.com`, which has no challenge. A 200 proved
  nothing.
- It threw away cookie attributes (domain, path, expiry, Secure, HttpOnly).
- "Challenge detected" was one substring check on a 403.
- There were no tests and no control target.
- The code printed "Bypass Successful!" on any 2xx, without defining success.

I kept the useful parts (Playwright acquisition, `curl_cffi` replay) and rebuilt
the rest around a target where the correct answer is known.

## The lab

`botlab/lab.py` runs a local HTTP server that issues a signed `lab_clearance`
cookie:

- The value is an HMAC over the expiry and the User-Agent.
- The cookie expires after a configurable TTL.
- The challenge page sets the cookie with JavaScript and reloads.
- The server returns `X-Lab-Reason: missing|expired|bad-signature|ok`, so a
  failed case can be identified instead of guessed at.

This is deliberately small. It is a test fixture, not a Cloudflare emulator.

## What I measured

Run on 2026-10-31 (UTC):

| Case | Cookie | User-Agent | Expected | Observed | Lab reason | Replay time |
|---|---|---|---|---|---|---|
| valid | valid | same | 200 ok | 200 ok | ok | 2.8 ms |
| no_cookie | none | same | 403 challenge | 403 challenge | missing | 1.5 ms |
| wrong_ua | valid | different | 403 challenge | 403 challenge | bad-signature | 1.6 ms |
| tampered | modified | same | 403 challenge | 403 challenge | bad-signature | 1.6 ms |
| expired | expired | same | 403 challenge | 403 challenge | expired | 1.9 ms |

Browser acquisition: **2.06 s**, final title `Protected content`, one clearance
cookie. The five replay cases matched their expected outcomes.

Raw output: [`experiments/results.json`](experiments/results.json)

Write-up: [`experiments/results.md`](experiments/results.md)

## What this does and does not show

**Shows:** the replay plumbing works under a toy model. A cookie acquired by a
real browser can be replayed by `curl_cffi` if the cookie jar and User-Agent
are preserved. Dropping the cookie, changing the UA, tampering with the value,
or using an expired value all fail, and the lab says why.

**Does not show:** that this bypasses Cloudflare. The lab does not model TLS/JA3
fingerprinting, IP reputation, `cf_clearance`'s real binding rules, CAPTCHA, or
Cloudflare's current challenge script. A real target may reject the same request
for reasons the lab cannot reproduce. The sample size is one local run.

That distinction is the main thing the first version got wrong.

## Reproduce

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

python -m unittest discover -s tests -v
python -m botlab experiment
```

`python -m botlab experiment` starts a local lab on a random port, acquires a
session with headless Chromium, runs the five replay cases, and writes
`experiments/results.json`. Use `--headed` to watch the browser.

Manual version:

```bash
# terminal 1
python -m botlab lab --port 8765 --ttl 60

# terminal 2
python -m botlab run --url http://127.0.0.1:8765/ --headed
```

Other commands:

```bash
python -m botlab acquire --url http://127.0.0.1:8765/ --out sessions/session.json
python -m botlab replay --session sessions/session.json --url http://127.0.0.1:8765/
```

## Layout

```text
botlab/
  lab.py        local signed-cookie challenge
  browser.py    Playwright session acquisition
  replay.py     curl_cffi replay
  session.py    full cookie/session model
  probe.py      response classifier
  cli.py        python -m botlab
experiments/
  results.md    measured run and observations
  results.json  raw output
tests/          19 tests
```

## Authorized use

Use this only on systems you own or have written permission to test. The
`--authorized` flag is a speed bump, not a security control: it exists so that
an accidental third-party URL does not become a default. This repository does
not include CAPTCHA solving, proxy rotation, credential attacks, or an
authentication bypass. It is a measurement harness for session replay.

## License

MIT
