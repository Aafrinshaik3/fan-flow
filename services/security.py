"""
Security helpers: input sanitization and a simple in-memory rate limiter.

These are intentionally dependency-light so the demo can run anywhere,
but the design (per-key sliding window, explicit size caps, no eval/exec,
no string-built queries or shell calls) reflects patterns that carry over
directly to a production deployment behind Redis.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from threading import Lock

# Characters that have no place in a chat/navigation query and are stripped
# defensively. This is a belt-and-braces measure -- the real trust boundary
# is that user input is NEVER concatenated into code, shell commands, or
# HTML without escaping; Flask/Jinja auto-escapes template output by default.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidationError(ValueError):
    """Raised when user-supplied input fails validation."""


def sanitize_text(raw: str, *, max_length: int, field_name: str = "input") -> str:
    """
    Validate and clean free-text user input.

    Raises ValidationError with a message safe to show to the end user.
    """
    if raw is None:
        raise ValidationError(f"{field_name} is required.")
    if not isinstance(raw, str):
        raise ValidationError(f"{field_name} must be text.")

    cleaned = _CONTROL_CHARS.sub("", raw).strip()

    if not cleaned:
        raise ValidationError(f"{field_name} cannot be empty.")
    if len(cleaned) > max_length:
        raise ValidationError(
            f"{field_name} is too long (max {max_length} characters)."
        )
    return cleaned


class RateLimiter:
    """
    Simple thread-safe sliding-window rate limiter, keyed by client identity
    (e.g. IP address). Suitable for a single-process demo; swap the internal
    store for Redis (INCR + EXPIRE) to run this across multiple workers.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True
