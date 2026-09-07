"""Same-origin guard for the P10.7b v2 Runtime execution boundary."""

from __future__ import annotations

from urllib.parse import urlsplit

from .http_security import is_loopback_host


INTENT = "p10-body-sway-spine42-v3-runtime-v2"


class P10Spine42V3RuntimeHttpSecurityV2Error(ValueError):
    """Public-safe rejection of request metadata."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_p10_spine42_v3_runtime_write_headers_v2(headers) -> None:
    """Require one explicit same-origin browser authorization request."""

    host = _one(headers, "Host", required=True, code="forbidden_host")
    if not _loopback_authority(host):
        _fail("forbidden_host", "Host must be loopback-local.")
    origin = _one(
        headers, "Origin", required=True, code="forbidden_origin",
    )
    if origin != f"http://{host}":
        _fail("forbidden_origin", "Origin must exactly match the local Host.")
    intent = _one(
        headers, "X-Autospine-Intent", required=True,
        code="forbidden_intent",
    )
    if intent != INTENT:
        _fail("forbidden_intent", "P10.7b v2 execution intent is missing.")
    site = _one(
        headers, "Sec-Fetch-Site", required=True,
        code="forbidden_fetch_site",
    )
    if site != "same-origin":
        _fail("forbidden_fetch_site", "Request must be same-origin.")


def require_p10_spine42_v3_runtime_read_headers_v2(headers) -> None:
    """Reject an explicitly cross-site read without requiring browser headers."""

    site = _one(
        headers, "Sec-Fetch-Site", required=False,
        code="forbidden_fetch_site",
    )
    if site is not None and site not in {"same-origin", "none"}:
        _fail("forbidden_fetch_site", "Request is not same-origin.")


def _one(headers, name, *, required, code):
    try:
        values = headers.get_all(name, []) or []
    except (AttributeError, TypeError, ValueError) as exc:
        raise P10Spine42V3RuntimeHttpSecurityV2Error(
            code, f"{name} header is invalid.",
        ) from exc
    if len(values) != 1:
        if not values and not required:
            return None
        _fail(code, f"Exactly one {name} header is required.")
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        _fail(code, f"{name} header is invalid.")
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


def _fail(code, message):
    raise P10Spine42V3RuntimeHttpSecurityV2Error(code, message)


__all__ = [
    "INTENT", "P10Spine42V3RuntimeHttpSecurityV2Error",
    "require_p10_spine42_v3_runtime_read_headers_v2",
    "require_p10_spine42_v3_runtime_write_headers_v2",
]
