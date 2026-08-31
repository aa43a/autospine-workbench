"""Same-origin and explicit-intent guard for official Runtime execution."""

from __future__ import annotations

from urllib.parse import urlsplit

from .http_security import is_loopback_host


INTENT = "p10-official-runtime-capture-v2"


class P10RuntimeCaptureHttpSecurityError(ValueError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_p10_runtime_capture_headers(headers) -> None:
    """Require exact local Origin/Host plus the one-run intent."""

    host = _one(headers, "Host", required=True, code="forbidden_host")
    if not _loopback_authority(host):
        raise P10RuntimeCaptureHttpSecurityError(
            "forbidden_host", "Host must be an explicit loopback authority."
        )
    origin = _one(headers, "Origin", required=True, code="forbidden_origin")
    if origin != f"http://{host}":
        raise P10RuntimeCaptureHttpSecurityError(
            "forbidden_origin", "Origin must exactly match the local Host."
        )
    intent = _one(
        headers, "X-Autospine-Intent", required=True,
        code="forbidden_intent",
    )
    if intent != INTENT:
        raise P10RuntimeCaptureHttpSecurityError(
            "forbidden_intent", "Official Runtime execution intent is missing."
        )
    fetch_site = _one(
        headers, "Sec-Fetch-Site", required=False,
        code="forbidden_fetch_site",
    )
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        raise P10RuntimeCaptureHttpSecurityError(
            "forbidden_fetch_site", "Runtime execution request is not same-origin."
        )


def _one(headers, name, *, required, code):
    try:
        values = headers.get_all(name, []) or []
    except (AttributeError, TypeError, ValueError) as exc:
        raise P10RuntimeCaptureHttpSecurityError(
            code, f"{name} header is invalid."
        ) from exc
    if len(values) != 1:
        if not values and not required:
            return None
        raise P10RuntimeCaptureHttpSecurityError(
            code, f"Exactly one {name} header is required."
        )
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise P10RuntimeCaptureHttpSecurityError(
            code, f"{name} header is invalid."
        )
    return value


def _loopback_authority(value):
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.hostname and is_loopback_host(parsed.hostname)
        and parsed.username is None and parsed.password is None
        and not parsed.path and not parsed.query and not parsed.fragment
        and (port is None or 0 <= port <= 65535)
    )


__all__ = [
    "INTENT", "P10RuntimeCaptureHttpSecurityError",
    "require_p10_runtime_capture_headers",
]
