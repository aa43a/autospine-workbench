"""Same-origin guard for package-bound P10.5c publication."""

from __future__ import annotations

from urllib.parse import urlsplit

from .http_security import is_loopback_host
from .seam_review_publication import INTENT_VALUE


INTENT_HEADER = "X-Autospine-Intent"


class SeamReviewPublicationHttpSecurityError(ValueError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_seam_review_publication_headers(headers) -> None:
    host = _one(headers, "Host", True, "forbidden_host")
    if not _loopback_authority(host):
        raise SeamReviewPublicationHttpSecurityError(
            "forbidden_host", "Host must be an explicit loopback authority."
        )
    origin = _one(headers, "Origin", True, "forbidden_origin")
    if origin != f"http://{host}":
        raise SeamReviewPublicationHttpSecurityError(
            "forbidden_origin", "Origin must exactly match the local Host."
        )
    intent = _one(headers, INTENT_HEADER, True, "forbidden_intent")
    if intent != INTENT_VALUE:
        raise SeamReviewPublicationHttpSecurityError(
            "forbidden_intent", "Reviewed seam publication intent is missing."
        )
    fetch_site = _one(headers, "Sec-Fetch-Site", False, "forbidden_fetch_site")
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        raise SeamReviewPublicationHttpSecurityError(
            "forbidden_fetch_site", "Publication request is not same-origin."
        )


def _one(headers, name, required, code):
    try:
        values = headers.get_all(name, []) or []
    except (AttributeError, TypeError, ValueError) as exc:
        raise SeamReviewPublicationHttpSecurityError(
            code, f"{name} header is invalid."
        ) from exc
    if len(values) != 1:
        if not values and not required:
            return None
        raise SeamReviewPublicationHttpSecurityError(
            code, f"Exactly one {name} header is required."
        )
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise SeamReviewPublicationHttpSecurityError(
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
