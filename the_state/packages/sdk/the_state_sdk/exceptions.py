from __future__ import annotations


class TheStateError(Exception):
    """Base error for all SDK failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NotFoundError(TheStateError):
    """A requested resource does not exist (HTTP 404)."""


class RateLimitError(TheStateError):
    """The caller has been rate limited (HTTP 429)."""
