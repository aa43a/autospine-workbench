"""Same-origin guard for state-writing P10.2b framing review."""

from __future__ import annotations

from urllib.parse import urlsplit

from .capture_framing_profile import INTENT
from .http_security import is_loopback_host


class CaptureFramingHttpSecurityError(ValueError):
    """Public-safe rejection of capture-framing request metadata."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_capture_framing_headers(headers) -> None:
    """Require exact loopback Host/Origin and one explicit intent header."""

    host = _one(headers, "Host", required=True, code="forbidden_host")
    if not _loopback_authority(host):
        raise CaptureFramingHttpSecurityError(
            "forbidden_host", "Host must be an explicit loopback authority."
        )
    origin = _one(headers, "Origin", required=True, code="forbidden_origin")
    if origin != f"http://{host}":
        raise CaptureFramingHttpSecurityError(
            "forbidden_origin", "Origin must exactly match the local Host."
        )
    intent = _one(
        headers, "X-Autospine-Intent",
        required=True, code="forbidden_intent",
    )
    if intent != INTENT:
        raise CaptureFramingHttpSecurityError(
            "forbidden_intent", "Capture-framing review intent is missing."
        )
    fetch_site = _one(
        headers, "Sec-Fetch-Site",
        required=False, code="forbidden_fetch_site",
    )
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        raise CaptureFramingHttpSecurityError(
            "forbidden_fetch_site", "Framing review request is not same-origin."
        )


def _one(headers, name: str, *, required: bool, code: str) -> str | None:
    try:
        values = headers.get_all(name, []) or []
    except (AttributeError, TypeError, ValueError) as exc:
        raise CaptureFramingHttpSecurityError(
            code, f"{name} header is invalid."
        ) from exc
    if len(values) != 1:
        if not values and not required:
            return None
        raise CaptureFramingHttpSecurityError(
            code, f"Exactly one {name} header is required."
        )
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise CaptureFramingHttpSecurityError(
            code, f"{name} header is invalid."
        )
    return value


def _loopback_authority(value: str) -> bool:
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
