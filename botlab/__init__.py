"""A controlled lab for browser-session replay experiments."""

from .probe import Outcome, Verdict, classify  # noqa: F401
from .session import Cookie, SessionData  # noqa: F401

__version__ = "0.2.0"
