"""Command-line interface for the replay lab."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from .browser import AcquisitionError, acquire_session
from .config import (
    DEFAULT_LAB_URL,
    DEFAULT_RESULTS_PATH,
    DEFAULT_SESSION_PATH,
    is_loopback_url,
)
from .lab import LabServer
from .lab import main as lab_main
from .replay import ReplayResult, replay
from .session import Cookie, SessionData


def _guard(url: str, authorized: bool) -> None:
    if not is_loopback_url(url) and not authorized:
        raise SystemExit(
            "Refusing a non-loopback target without --authorized.\n"
            "Use this only on systems you own or have written permission to test."
        )


def _session_summary(session: SessionData, elapsed_s: float | None = None) -> None:
    clearance = len(session.clearance_cookies)
    print(f"[*] browser session: solved={session.solved}")
    print(f"    final URL: {session.final_url}")
    print(f"    title:     {session.title!r}")
    print(f"    cookies:   {len(session.cookies)} ({clearance} clearance)")
    if elapsed_s is not None:
        print(f"    acquisition: {elapsed_s:.2f}s")
    print(f"    user-agent:{session.user_agent[:110]}")


def _result_line(name: str, result: ReplayResult) -> str:
    status = "-" if result.status is None else str(result.status)
    lab = f"lab={result.lab_reason}" if result.lab_reason else ""
    return (
        f"{name:<12} {status:>4}  {result.outcome.value:<10} "
        f"{result.elapsed_ms:8.1f} ms  {lab:<16} {result.reason}"
    )


def _print_result(name: str, result: ReplayResult) -> None:
    print(_result_line(name, result))


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _save_results(path: str, payload: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def cmd_lab(args) -> int:
    return lab_main(["--host", args.host, "--port", str(args.port),
                     "--ttl", str(args.ttl)])


def _headless(args) -> bool:
    return bool(getattr(args, "headless", False) or not getattr(args, "headed", False))


def cmd_acquire(args) -> int:
    _guard(args.url, args.authorized)
    started = time.perf_counter()
    try:
        session = acquire_session(
            args.url,
            headless=_headless(args),
            timeout=args.timeout,
        )
    except AcquisitionError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1

    _session_summary(session, time.perf_counter() - started)
    if args.out:
        session.save(args.out)
        print(f"[*] session saved to {args.out}")
    return 0 if session.solved else 2


def cmd_replay(args) -> int:
    _guard(args.url, args.authorized)
    try:
        session = SessionData.load(args.session)
    except (OSError, ValueError) as exc:
        print(f"[!] could not read {args.session}: {exc}", file=sys.stderr)
        return 1

    result = replay(session, args.url, timeout=args.timeout)
    _print_result("replay", result)
    return 0 if result.outcome.value == "ok" else 1


def cmd_run(args) -> int:
    _guard(args.url, args.authorized)
    started = time.perf_counter()
    try:
        session = acquire_session(
            args.url,
            headless=_headless(args),
            timeout=args.timeout,
        )
    except AcquisitionError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1

    _session_summary(session, time.perf_counter() - started)
    if args.out:
        session.save(args.out)
        print(f"[*] session saved to {args.out}")

    result = replay(session, args.url, timeout=args.timeout)
    _print_result("replay", result)
    return 0 if session.solved and result.outcome.value == "ok" else 1


def _experiment_cases(session: SessionData, lab: LabServer | None):
    cases: list[tuple[str, SessionData]] = [("valid", session)]
    cases.append(("no_cookie", replace(session, cookies=[])))
    cases.append((
        "wrong_ua",
        replace(
            session,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
        ),
    ))

    tampered = []
    for cookie in session.cookies:
        if cookie.name in ("lab_clearance", "cf_clearance") and cookie.value:
            replacement = cookie.value[:-1] + (
                "0" if cookie.value[-1] != "0" else "1"
            )
            tampered.append(replace(cookie, value=replacement))
        else:
            tampered.append(cookie)
    if any(c.name in ("lab_clearance", "cf_clearance") for c in tampered):
        cases.append(("tampered", replace(session, cookies=tampered)))

    if lab is not None:
        expired = [c for c in session.cookies if c.name != "lab_clearance"]
        expired.append(lab.expired_cookie(session.user_agent))
        cases.append(("expired", replace(session, cookies=expired)))

    return cases


EXPECTED_OUTCOMES = {
    "valid": "ok",
    "no_cookie": "challenge",
    "wrong_ua": "challenge",
    "tampered": "challenge",
    "expired": "challenge",
}


def cmd_experiment(args) -> int:
    lab: LabServer | None = None
    if args.url:
        _guard(args.url, args.authorized)
        url = args.url
    else:
        lab = LabServer(ttl=args.ttl, quiet=True).start()
        url = lab.url
        print(f"[*] local lab: {url} (ttl={args.ttl:.0f}s)")

    try:
        started = time.perf_counter()
        session = acquire_session(
            url,
            headless=_headless(args),
            timeout=args.timeout,
        )
        acquisition_s = time.perf_counter() - started
        _session_summary(session, acquisition_s)

        print()
        print(f"{'case':<12} {'http':>4}  {'outcome':<10} {'time':>9}  "
              f"{'lab':<16} reason")
        print("-" * 88)

        rows = []
        for name, case_session in _experiment_cases(session, lab):
            result = replay(case_session, url, timeout=args.timeout)
            rows.append((name, result))
            _print_result(name, result)

        matched = sum(
            1 for name, result in rows
            if result.outcome.value == EXPECTED_OUTCOMES.get(name)
        )
        print(f"[*] expected outcomes: {matched}/{len(rows)}")

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "target": url,
            "controlled_lab": lab is not None,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "curl_cffi": _package_version("curl_cffi"),
                "playwright": _package_version("playwright"),
            },
            "browser_acquisition_s": round(acquisition_s, 2),
            "session": {
                "solved": session.solved,
                "title": session.title,
                "final_url": session.final_url,
                "cookie_count": len(session.cookies),
                "clearance_cookie_count": len(session.clearance_cookies),
                "user_agent": session.user_agent,
            },
            "expected_matched": matched,
            "expected_total": len(rows),
            "cases": [
                {
                    "case": name,
                    "expected_outcome": EXPECTED_OUTCOMES.get(name),
                    "status": result.status,
                    "outcome": result.outcome.value,
                    "reason": result.reason,
                    "lab_reason": result.lab_reason,
                    "elapsed_ms": round(result.elapsed_ms, 2),
                    "content_length": result.content_length,
                }
                for name, result in rows
            ],
        }
        _save_results(args.json, payload)
        print(f"[*] results written to {args.json}")

        return 0 if matched == len(rows) else 1
    except AcquisitionError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    finally:
        if lab is not None:
            lab.stop()


def _add_browser_mode(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--headed", action="store_true", help="show the browser")
    group.add_argument("--headless", action="store_true",
                       help="hide the browser (default)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m botlab",
        description=(
            "A local lab for testing whether a browser-issued clearance cookie "
            "can be replayed by curl_cffi."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lab = sub.add_parser("lab", help="run the local challenge server")
    lab.add_argument("--host", default="127.0.0.1")
    lab.add_argument("--port", type=int, default=8765)
    lab.add_argument("--ttl", type=float, default=60.0)
    lab.set_defaults(func=cmd_lab)

    acquire = sub.add_parser("acquire", help="get a session with a browser")
    acquire.add_argument("--url", default=DEFAULT_LAB_URL)
    acquire.add_argument("--out", default=DEFAULT_SESSION_PATH)
    _add_browser_mode(acquire)
    acquire.add_argument("--timeout", type=float, default=20.0)
    acquire.add_argument("--authorized", action="store_true")
    acquire.set_defaults(func=cmd_acquire)

    replay_cmd = sub.add_parser("replay", help="replay a stored session")
    replay_cmd.add_argument("--session", default=DEFAULT_SESSION_PATH)
    replay_cmd.add_argument("--url", default=DEFAULT_LAB_URL)
    replay_cmd.add_argument("--timeout", type=float, default=15.0)
    replay_cmd.add_argument("--authorized", action="store_true")
    replay_cmd.set_defaults(func=cmd_replay)

    run = sub.add_parser("run", help="acquire a session, then replay it")
    run.add_argument("--url", default=DEFAULT_LAB_URL)
    run.add_argument("--out", default="")
    _add_browser_mode(run)
    run.add_argument("--timeout", type=float, default=20.0)
    run.add_argument("--authorized", action="store_true")
    run.set_defaults(func=cmd_run)

    experiment = sub.add_parser(
        "experiment",
        help="run the valid/missing/wrong-UA/tampered/expired matrix",
    )
    experiment.add_argument("--url", default="",
                            help="target URL (default: start a local lab)")
    experiment.add_argument("--json", default=DEFAULT_RESULTS_PATH)
    _add_browser_mode(experiment)
    experiment.add_argument("--timeout", type=float, default=20.0)
    experiment.add_argument("--ttl", type=float, default=60.0)
    experiment.add_argument("--authorized", action="store_true")
    experiment.set_defaults(func=cmd_experiment)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
