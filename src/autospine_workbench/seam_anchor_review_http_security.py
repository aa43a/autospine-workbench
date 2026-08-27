"""Same-origin mutation guard for the local seam-anchor review API."""

from __future__ import annotations

from urllib.parse import urlsplit

from .http_security import is_loopback_host


INTENT_HEADER = "X-Autospine-Intent"
INTENT_VALUE = "seam-anchor-review"


class SeamAnchorReviewHttpSecurityError(ValueError):
    """A bounded, public-safe rejection of mutation metadata."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_seam_anchor_review_mutation_headers(headers) -> None:
    """Require one exact local Host/Origin pair and explicit user intent."""

    host = _one(headers, "Host", required=True, error_code="forbidden_host")
    if not _is_loopback_authority(host):
        raise SeamAnchorReviewHttpSecurityError(
            "forbidden_host", "Host must be an explicit loopback-local authority."
        )
    origin = _one(
        headers, "Origin", required=True, error_code="forbidden_origin"
    )
    if origin != f"http://{host}":
        raise SeamAnchorReviewHttpSecurityError(
            "forbidden_origin", "Origin must exactly match the local Host."
        )
    intent = _one(
        headers, INTENT_HEADER, required=True, error_code="forbidden_intent"
    )
    if intent != INTENT_VALUE:
        raise SeamAnchorReviewHttpSecurityError(
            "forbidden_intent", "Seam review mutation intent is missing."
        )
    fetch_site = _one(
        headers, "Sec-Fetch-Site", required=False,
        error_code="forbidden_fetch_site",
    )
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        raise SeamAnchorReviewHttpSecurityError(
            "forbidden_fetch_site", "Seam review mutation is not same-origin."
        )


def seam_anchor_review_cors_origin(headers) -> str | None:
    """Return an origin only when it exactly matches the local Host."""

    try:
        host = _one(headers, "Host", required=True, error_code="forbidden_host")
        origin = _one(
            headers, "Origin", required=False, error_code="forbidden_origin"
        )
    except SeamAnchorReviewHttpSecurityError:
        return None
    if not _is_loopback_authority(host) or origin != f"http://{host}":
        return None
    return origin


def _one(headers, name: str, *, required: bool, error_code: str) -> str | None:
    try:
        values = headers.get_all(name, [])
    except (AttributeError, TypeError, ValueError) as exc:
        raise SeamAnchorReviewHttpSecurityError(
            error_code, f"{name} header is invalid."
        ) from exc
    if values is None:
        values = []
    if len(values) != 1:
        if not values and not required:
            return None
        raise SeamAnchorReviewHttpSecurityError(
            error_code, f"Exactly one {name} header is required."
        )
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise SeamAnchorReviewHttpSecurityError(
            error_code, f"{name} header is invalid."
        )
    return value


def _is_loopback_authority(value: str) -> bool:
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.hostname
        and is_loopback_host(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and (port is None or 0 <= port <= 65535)
    )
